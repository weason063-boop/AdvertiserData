import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from api.database import SessionLocal, ensure_feishu_receivable_bills_table
from api.models import FeishuReceivableBill
from api.services.feishu_bitable_client import FeishuBitableClient


load_dotenv()


DEFAULT_RECEIVABLE_WIKI_TOKEN = "JzENwVhjOi9MTokI3q8cts2qnAb"
DEFAULT_BILL_SEND_TABLE_ID = "tblR4LR6twvs0uEV"
DEFAULT_CLIENT_ADVANCE_TABLE_ID = "tblOBxVXyoQThi0O"

INVALID_APPROVAL_STATUSES = {"已拒绝", "已撤回"}
COMPLETED_APPROVAL_STATUS = "已通过"
COLLECTION_NODE_KEYWORDS = ("回款", "应收账款", "应收账单")
RESOURCE_PACKAGE_YES_VALUES = {"是", "是的", "全部是", "yes", "y", "true", "1"}
RESOURCE_PACKAGE_QUOTE_AMOUNT_FIELDS = ("对客户的媒介报价金额", "对客户媒介报价金额")


@dataclass(frozen=True)
class ReceivableTableConfig:
    flow_type: str
    table_name: str
    table_id: str


class ReceivableSyncService:
    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID", "")
        self.app_secret = os.getenv("FEISHU_APP_SECRET", "")
        self.wiki_token = os.getenv("FEISHU_RECEIVABLE_WIKI_TOKEN", DEFAULT_RECEIVABLE_WIKI_TOKEN)
        self.app_token = os.getenv("FEISHU_RECEIVABLE_APP_TOKEN", "")
        self.bill_send_table_id = os.getenv("FEISHU_RECEIVABLE_BILL_TABLE_ID", DEFAULT_BILL_SEND_TABLE_ID)
        self.client_advance_table_id = os.getenv(
            "FEISHU_RECEIVABLE_ADVANCE_TABLE_ID",
            DEFAULT_CLIENT_ADVANCE_TABLE_ID,
        )
        self.client = FeishuBitableClient(self.app_id, self.app_secret)

    @property
    def table_configs(self) -> tuple[ReceivableTableConfig, ...]:
        return (
            ReceivableTableConfig("bill_send", "账单发送", self.bill_send_table_id),
            ReceivableTableConfig("client_advance", "（客户）垫付申请", self.client_advance_table_id),
        )

    def sync_all(self, db: Session | None = None) -> dict[str, Any]:
        """
        Refresh local receivable snapshots from the configured Feishu Bitable.
        The sync is intentionally isolated from billing calculation tables.
        """
        should_close = False
        if db is None:
            ensure_feishu_receivable_bills_table()
            db = SessionLocal()
            should_close = True

        try:
            tenant_token = self.client.get_tenant_access_token()
            app_token = self._resolve_app_token(tenant_token)
            synced_at = datetime.now()
            new_rows: list[FeishuReceivableBill] = []
            table_counts: dict[str, int] = {}

            for config in self.table_configs:
                records = self.client.list_records(tenant_token, app_token, config.table_id)
                table_counts[config.table_name] = len(records)
                for record in records:
                    row = self._build_row(
                        app_token=app_token,
                        config=config,
                        record=record,
                        synced_at=synced_at,
                    )
                    if row:
                        new_rows.append(row)

            target_table_ids = [config.table_id for config in self.table_configs]
            db.query(FeishuReceivableBill).filter(
                FeishuReceivableBill.source_token == app_token,
                FeishuReceivableBill.table_id.in_(target_table_ids),
            ).delete(synchronize_session=False)
            db.add_all(new_rows)
            db.commit()

            summary = self.get_summary(db)
            return {
                "status": "ok",
                "message": "飞书应收/逾期数据同步完成",
                "source_token": app_token,
                "synced_records": len(new_rows),
                "table_counts": table_counts,
                "summary": summary,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            if should_close:
                db.close()

    def get_summary(self, db: Session | None = None) -> dict[str, Any]:
        should_close = False
        if db is None:
            ensure_feishu_receivable_bills_table()
            db = SessionLocal()
            should_close = True
        try:
            rows = self._scoped_query(db).all()
            total_records = len(rows)
            active_rows = [row for row in rows if row.is_active]
            outstanding_rows = [row for row in active_rows if row.is_outstanding and float(row.outstanding_amount or 0) > 0]
            overdue_rows = [row for row in active_rows if row.is_overdue and float(row.overdue_amount or 0) > 0]

            latest_row = self._scoped_query(db).order_by(desc(FeishuReceivableBill.synced_at)).first()
            return {
                "total_records": total_records,
                "active_records": len(active_rows),
                "outstanding": {
                    "count": len(outstanding_rows),
                    "amount_by_currency": self._sum_by_currency(outstanding_rows, "outstanding_amount"),
                },
                "overdue": {
                    "count": len(overdue_rows),
                    "amount_by_currency": self._sum_by_currency(overdue_rows, "overdue_amount"),
                    "max_overdue_days": max((int(row.overdue_days or 0) for row in overdue_rows), default=0),
                    "aging_buckets": self._build_aging_buckets(overdue_rows),
                },
                "by_flow": self._build_flow_summary(active_rows),
                "top_overdue": [self._serialize_row(row) for row in self._top_overdue_rows(overdue_rows)],
                "synced_at": latest_row.synced_at.isoformat() if latest_row and latest_row.synced_at else None,
            }
        finally:
            if should_close:
                db.close()

    def list_bills(
        self,
        *,
        status: str = "overdue",
        limit: int = 100,
        client_name: str | None = None,
        db: Session | None = None,
    ) -> list[dict[str, Any]]:
        should_close = False
        if db is None:
            ensure_feishu_receivable_bills_table()
            db = SessionLocal()
            should_close = True
        try:
            safe_limit = max(1, min(500, int(limit or 100)))
            query = self._scoped_query(db).filter(FeishuReceivableBill.is_active.is_(True))
            query = query.filter(
                or_(
                    FeishuReceivableBill.approval_status.is_(None),
                    FeishuReceivableBill.approval_status != COMPLETED_APPROVAL_STATUS,
                )
            )
            if client_name:
                query = query.filter(FeishuReceivableBill.client_name == str(client_name).strip())
            if status == "overdue":
                query = query.filter(FeishuReceivableBill.is_overdue.is_(True))
                query = query.order_by(desc(FeishuReceivableBill.overdue_amount), desc(FeishuReceivableBill.overdue_days))
            elif status == "outstanding":
                query = query.filter(FeishuReceivableBill.is_outstanding.is_(True))
                query = query.order_by(desc(FeishuReceivableBill.outstanding_amount), desc(FeishuReceivableBill.overdue_days))
            else:
                query = query.order_by(desc(FeishuReceivableBill.outstanding_amount), desc(FeishuReceivableBill.overdue_amount))
            rows = query.limit(safe_limit).all()
            return [self._serialize_row(row) for row in rows]
        finally:
            if should_close:
                db.close()

    def get_client_summary(
        self,
        *,
        metric: str = "overdue",
        limit: int = 100,
        db: Session | None = None,
    ) -> dict[str, Any]:
        should_close = False
        if db is None:
            ensure_feishu_receivable_bills_table()
            db = SessionLocal()
            should_close = True
        try:
            rows = self._scoped_query(db).filter(FeishuReceivableBill.is_active.is_(True)).all()
            clients: dict[str, list[FeishuReceivableBill]] = defaultdict(list)
            for row in rows:
                if not row.client_name:
                    continue
                if not row.is_outstanding and not row.is_overdue:
                    continue
                clients[row.client_name].append(row)

            safe_limit = max(1, min(500, int(limit or 100)))
            client_rows: list[dict[str, Any]] = []
            for client_name, client_bills in clients.items():
                outstanding_rows = [
                    row for row in client_bills
                    if row.is_outstanding and float(row.outstanding_amount or 0.0) > 0
                ]
                overdue_rows = [
                    row for row in client_bills
                    if row.is_overdue and float(row.overdue_amount or 0.0) > 0
                ]
                if not outstanding_rows and not overdue_rows:
                    continue
                owners = sorted({
                    str(row.owner_name or "").strip()
                    for row in client_bills
                    if str(row.owner_name or "").strip()
                })
                item = {
                    "client_name": client_name,
                    "owner_names": owners,
                    "bill_count": len(client_bills),
                    "outstanding_count": len(outstanding_rows),
                    "overdue_count": len(overdue_rows),
                    "outstanding_amount_by_currency": self._sum_by_currency(outstanding_rows, "outstanding_amount"),
                    "overdue_amount_by_currency": self._sum_by_currency(overdue_rows, "overdue_amount"),
                    "max_overdue_days": max((int(row.overdue_days or 0) for row in overdue_rows), default=0),
                    "_sort_score": self._client_sort_score(metric, outstanding_rows, overdue_rows),
                }
                client_rows.append(item)

            client_rows.sort(key=lambda item: (float(item.get("_sort_score") or 0.0), int(item.get("max_overdue_days") or 0)), reverse=True)
            for item in client_rows:
                item.pop("_sort_score", None)
            return {
                "metric": metric,
                "limit": safe_limit,
                "rows": client_rows[:safe_limit],
            }
        finally:
            if should_close:
                db.close()

    @staticmethod
    def _client_sort_score(
        metric: str,
        outstanding_rows: list[FeishuReceivableBill],
        overdue_rows: list[FeishuReceivableBill],
    ) -> float:
        target_rows = overdue_rows if metric == "overdue" else outstanding_rows
        target_field = "overdue_amount" if metric == "overdue" else "outstanding_amount"
        return sum(float(getattr(row, target_field) or 0.0) for row in target_rows)

    def _resolve_app_token(self, tenant_token: str) -> str:
        if self.app_token:
            return self.app_token
        obj_type, obj_token = self.client.resolve_wiki_token(tenant_token, self.wiki_token)
        if obj_type != "bitable" or not obj_token:
            raise RuntimeError("Configured Feishu receivable wiki token does not resolve to a Bitable")
        return str(obj_token)

    def _scoped_query(self, db: Session):
        table_ids = [config.table_id for config in self.table_configs if config.table_id]
        query = db.query(FeishuReceivableBill)
        if not table_ids:
            return query.filter(FeishuReceivableBill.id == -1)

        query = query.filter(FeishuReceivableBill.table_id.in_(table_ids))
        latest_source = (
            db.query(FeishuReceivableBill.source_token)
            .filter(FeishuReceivableBill.table_id.in_(table_ids))
            .order_by(desc(FeishuReceivableBill.synced_at))
            .first()
        )
        if latest_source and latest_source[0]:
            query = query.filter(FeishuReceivableBill.source_token == latest_source[0])
        return query

    def _build_row(
        self,
        *,
        app_token: str,
        config: ReceivableTableConfig,
        record: dict[str, Any],
        synced_at: datetime,
    ) -> FeishuReceivableBill | None:
        record_id = str(record.get("record_id") or "").strip()
        fields = record.get("fields") or {}
        if not record_id or not isinstance(fields, dict):
            return None

        status = self._text(fields.get("申请状态"))
        node = self._text(fields.get("审批节点"))
        active = status not in INVALID_APPROVAL_STATUSES
        amount = self._extract_amount(config.flow_type, fields)
        due_date_value, due_date_text = self._extract_due_date(config.flow_type, fields)
        outstanding = self._calculate_outstanding_amount(active, status, node, amount)
        overdue_days = self._calculate_overdue_days(due_date_value)
        is_overdue = outstanding > 0 and overdue_days > 0
        overdue_amount = outstanding if is_overdue else 0.0
        currency = self._text(fields.get("币种") or fields.get("账单币种") or fields.get("币种1"))
        currency_code = self._normalize_currency_code(currency)

        return FeishuReceivableBill(
            source_type="feishu_bitable",
            source_token=app_token,
            table_id=config.table_id,
            table_name=config.table_name,
            record_id=record_id,
            flow_type=config.flow_type,
            source_id=self._text(fields.get("SourceID")),
            application_no=self._application_text(fields.get("申请编号")),
            approval_status=status,
            approval_node=node,
            client_name=self._text(fields.get("客户简称") or fields.get("客户简称1")),
            project_name=self._text(fields.get("项目简称")),
            business_type=self._text(fields.get("业务类型")),
            department=self._text(fields.get("账单所属部门") or fields.get("发起人部门")),
            owner_name=self._person_names(fields.get("BD/CS对接人") or fields.get("当前处理人") or fields.get("发起人")),
            bill_type=self._text(fields.get("账单类型") or fields.get("是否为资源包垫付")),
            currency=currency,
            currency_code=currency_code,
            amount=amount,
            outstanding_amount=outstanding,
            overdue_amount=overdue_amount,
            overdue_days=overdue_days,
            is_active=active,
            is_outstanding=outstanding > 0,
            is_overdue=is_overdue,
            due_date=due_date_value.isoformat() if due_date_value else None,
            due_date_text=due_date_text,
            initiated_at=self._datetime_from_feishu(fields.get("发起时间")),
            completed_at=self._datetime_from_feishu(fields.get("完成时间")),
            raw_fields_json=json.dumps(fields, ensure_ascii=False, default=str),
            synced_at=synced_at,
        )

    def _extract_amount(self, flow_type: str, fields: dict[str, Any]) -> float:
        if flow_type == "bill_send":
            if "账单金额" in fields:
                return self._number(fields.get("账单金额"))
            return self._number(fields.get("账单金额1"))

        if "垫付金额(去重)" in fields:
            amount = self._number(fields.get("垫付金额(去重)"))
        else:
            amount = self._number(fields.get("垫付金额"))

        if amount <= 0 and self._is_resource_package_advance(fields):
            for field_name in RESOURCE_PACKAGE_QUOTE_AMOUNT_FIELDS:
                quote_amount = self._number(fields.get(field_name))
                if quote_amount > 0:
                    return quote_amount
        return amount

    def _is_resource_package_advance(self, fields: dict[str, Any]) -> bool:
        value = self._text(fields.get("是否为资源包垫付")).strip().lower()
        return value in RESOURCE_PACKAGE_YES_VALUES

    def _extract_due_date(self, flow_type: str, fields: dict[str, Any]) -> tuple[date | None, str]:
        if flow_type == "client_advance":
            value = fields.get("回款时间1") or fields.get("回款时间")
        else:
            value = fields.get("回款时间")
        return self._date_from_feishu(value), self._text(value)

    def _calculate_outstanding_amount(self, active: bool, status: str, node: str, amount: float) -> float:
        if not active or amount <= 0:
            return 0.0
        has_collection_node = any(keyword in node for keyword in COLLECTION_NODE_KEYWORDS)
        if status != COMPLETED_APPROVAL_STATUS or has_collection_node:
            return amount
        return 0.0

    @staticmethod
    def _calculate_overdue_days(due_date: date | None) -> int:
        if not due_date:
            return 0
        return max((date.today() - due_date).days, 0)

    @staticmethod
    def _sum_by_currency(rows: list[FeishuReceivableBill], amount_field: str) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            code = row.currency_code or row.currency or "UNKNOWN"
            if code not in grouped:
                grouped[code] = {
                    "currency_code": code,
                    "currency": row.currency or code,
                    "amount": 0.0,
                    "count": 0,
                }
            grouped[code]["amount"] += float(getattr(row, amount_field) or 0.0)
            grouped[code]["count"] += 1
        return sorted(
            (
                {**item, "amount": round(float(item["amount"]), 2)}
                for item in grouped.values()
                if abs(float(item["amount"])) > 1e-9
            ),
            key=lambda item: float(item["amount"]),
            reverse=True,
        )

    def _build_aging_buckets(self, rows: list[FeishuReceivableBill]) -> list[dict[str, Any]]:
        bucket_defs = (
            ("d1_7", "1-7天", 1, 7),
            ("d8_30", "8-30天", 8, 30),
            ("d31_60", "31-60天", 31, 60),
            ("d60_plus", "60天以上", 61, None),
        )
        grouped: dict[str, list[FeishuReceivableBill]] = {key: [] for key, *_ in bucket_defs}
        for row in rows:
            days = int(row.overdue_days or 0)
            if days <= 0:
                continue
            for key, _label, min_days, max_days in bucket_defs:
                if days >= min_days and (max_days is None or days <= max_days):
                    grouped[key].append(row)
                    break

        result: list[dict[str, Any]] = []
        for key, label, min_days, max_days in bucket_defs:
            bucket_rows = grouped[key]
            if not bucket_rows:
                continue
            result.append(
                {
                    "key": key,
                    "label": label,
                    "min_days": min_days,
                    "max_days": max_days,
                    "count": len(bucket_rows),
                    "amount_by_currency": self._sum_by_currency(bucket_rows, "overdue_amount"),
                }
            )
        return result

    def _build_flow_summary(self, rows: list[FeishuReceivableBill]) -> list[dict[str, Any]]:
        grouped: dict[str, list[FeishuReceivableBill]] = defaultdict(list)
        for row in rows:
            grouped[row.flow_type or "unknown"].append(row)
        result: list[dict[str, Any]] = []
        for flow_type, flow_rows in grouped.items():
            result.append(
                {
                    "flow_type": flow_type,
                    "count": len(flow_rows),
                    "outstanding": self._sum_by_currency(
                        [row for row in flow_rows if row.is_outstanding],
                        "outstanding_amount",
                    ),
                    "overdue": self._sum_by_currency(
                        [row for row in flow_rows if row.is_overdue],
                        "overdue_amount",
                    ),
                }
            )
        return sorted(result, key=lambda item: item["flow_type"])

    @staticmethod
    def _top_overdue_rows(rows: list[FeishuReceivableBill]) -> list[FeishuReceivableBill]:
        return sorted(
            rows,
            key=lambda row: (float(row.overdue_amount or 0.0), int(row.overdue_days or 0)),
            reverse=True,
        )[:10]

    @staticmethod
    def _serialize_row(row: FeishuReceivableBill) -> dict[str, Any]:
        return {
            "record_id": row.record_id,
            "table_name": row.table_name,
            "application_no": row.application_no,
            "client_name": row.client_name,
            "project_name": row.project_name,
            "flow_type": row.flow_type,
            "approval_status": row.approval_status,
            "approval_node": row.approval_node,
            "currency": row.currency,
            "currency_code": row.currency_code,
            "amount": float(row.amount or 0.0),
            "outstanding_amount": float(row.outstanding_amount or 0.0),
            "overdue_amount": float(row.overdue_amount or 0.0),
            "overdue_days": int(row.overdue_days or 0),
            "due_date": row.due_date,
            "owner_name": row.owner_name,
        }

    @staticmethod
    def _text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            parts: list[str] = []
            for item in value:
                if isinstance(item, dict):
                    parts.append(str(item.get("text") or item.get("name") or item.get("en_name") or ""))
                else:
                    parts.append(str(item))
            return "".join(parts).strip()
        if isinstance(value, dict):
            return str(value.get("text") or value.get("name") or value.get("link") or "").strip()
        return str(value).strip()

    @classmethod
    def _person_names(cls, value: Any) -> str:
        if isinstance(value, list):
            names = []
            for item in value:
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("en_name") or item.get("email") or "").strip()
                    if name:
                        names.append(name)
            return "、".join(names)
        return cls._text(value)

    @classmethod
    def _application_text(cls, value: Any) -> str:
        if isinstance(value, dict):
            return str(value.get("text") or value.get("link") or "").strip()
        return cls._text(value)

    @staticmethod
    def _number(value: Any) -> float:
        if value is None or value == "":
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).replace(",", "").strip())
        except Exception:
            return 0.0

    @classmethod
    def _date_from_feishu(cls, value: Any) -> date | None:
        dt = cls._datetime_from_feishu(value)
        if dt:
            return dt.date()
        text = cls._text(value)
        if not text:
            return None
        today = date.today()
        patterns = (
            r"(?P<year>20\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})",
            r"(?P<year>20\d{2})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日?",
            r"(?P<month>\d{1,2})[./-](?P<day>\d{1,2})",
            r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日?",
        )
        for pattern in patterns:
            match = re.search(pattern, text)
            if not match:
                continue
            year = int(match.groupdict().get("year") or today.year)
            month = int(match.group("month"))
            day = int(match.group("day"))
            try:
                return date(year, month, day)
            except ValueError:
                return None
        return None

    @staticmethod
    def _datetime_from_feishu(value: Any) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            number = float(value)
        else:
            text = str(value).strip()
            if not re.fullmatch(r"\d{10,13}", text):
                return None
            number = float(text)
        if number > 10_000_000_000:
            number = number / 1000
        try:
            return datetime.fromtimestamp(number)
        except Exception:
            return None

    @staticmethod
    def _normalize_currency_code(currency: str) -> str:
        text = (currency or "").strip().upper()
        if "USD" in text or "美金" in text or "美元" in text:
            return "USD"
        if "RMB" in text or "CNY" in text or "人民币" in text:
            return "RMB"
        if "EUR" in text or "欧元" in text:
            return "EUR"
        if "AUD" in text or "澳元" in text:
            return "AUD"
        if "GBP" in text or "英镑" in text:
            return "GBP"
        if "JPY" in text or "日元" in text:
            return "JPY"
        return text or "UNKNOWN"
