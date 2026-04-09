# -*- coding: utf-8 -*-
"""Excel/Feishu contract migration helpers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.exc import OperationalError

from .database import SessionLocal, upsert_client
from .models import ClientContractLine

logger = logging.getLogger(__name__)

_EMPTY_CLAUSE_VALUES = {"", "/", "-", "无", "none", "null", "nan"}


def migrate_client_data(data: list) -> int:
    """批量迁移客户数据到 clients 表。"""
    count = 0
    for row in data:
        name = _to_text(row.get("name"))
        if not name:
            continue

        upsert_client(
            name=name,
            business_type=str(row.get("business_type")) if row.get("business_type") else None,
            department=str(row.get("department")) if row.get("department") else None,
            entity=str(row.get("entity")) if row.get("entity") else None,
            fee_clause=str(row.get("fee_clause")) if row.get("fee_clause") else None,
        )
        count += 1
    return count


def _to_text(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, (list, tuple, set)):
        parts = [str(v).strip() for v in value if v is not None and str(v).strip()]
        return " ".join(parts) if parts else None

    if isinstance(value, dict):
        text = str(value).strip()
        return text if text else None

    if not pd.api.types.is_scalar(value):
        text = str(value).strip()
        return text if text else None

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text = str(value).strip()
    return text if text else None


def _has_non_empty_clause(value: Any) -> bool:
    text = _to_text(value)
    if not text:
        return False
    return text.lower() not in _EMPTY_CLAUSE_VALUES


def _is_ad_business_type(value: Any) -> bool:
    text = _to_text(value)
    if not text:
        return False
    return "广告" in text


def _pick_preferred_contract_line(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    同一客户多行时，选择最合适的一行落到 legacy clients 表：
    1) 广告业务优先
    2) 有服务费条款优先
    3) 保持源行顺序稳定
    """
    if not rows:
        return {}

    def _sort_key(row: dict[str, Any]) -> tuple[int, int, int]:
        row_idx = row.get("_source_row_index")
        if row_idx is None:
            row_idx = 10**9
        return (
            0 if _is_ad_business_type(row.get("business_type")) else 1,
            0 if _has_non_empty_clause(row.get("fee_clause")) else 1,
            int(row_idx),
        )

    return sorted(rows, key=_sort_key)[0]


def migrate_feishu_contract_lines(
    data: list,
    source_token: str,
    source_type: str = "feishu_sheet",
) -> dict[str, int]:
    """
    逐行写入 client_contract_lines，并聚合回 clients（兼容旧逻辑）。
    """
    db = SessionLocal()
    source_token = _to_text(source_token) or "unknown_source"
    inserted_rows: list[dict[str, Any]] = []
    clients_map: dict[str, list[dict[str, Any]]] = {}

    try:
        db.query(ClientContractLine).filter(
            ClientContractLine.source_type == source_type,
            ClientContractLine.source_token == source_token,
        ).delete(synchronize_session=False)

        for seq, row in enumerate(data, start=1):
            name = _to_text(row.get("name"))
            if not name:
                continue

            source_row_index = row.get("_source_row_index")
            if source_row_index is None:
                source_row_index = seq

            line_payload = {
                "name": name,
                "business_type": _to_text(row.get("business_type")),
                "department": _to_text(row.get("department")),
                "entity": _to_text(row.get("entity")),
                "fee_clause": _to_text(row.get("fee_clause")),
                "payment_term": _to_text(row.get("payment_term")),
                "_source_row_index": int(source_row_index),
            }
            inserted_rows.append(line_payload)
            clients_map.setdefault(name, []).append(line_payload)

            db.add(
                ClientContractLine(
                    source_type=source_type,
                    source_token=source_token,
                    source_row_index=int(source_row_index),
                    client_name=name,
                    business_type=line_payload["business_type"],
                    department=line_payload["department"],
                    entity=line_payload["entity"],
                    fee_clause=line_payload["fee_clause"],
                    payment_term=line_payload["payment_term"],
                )
            )

        for client_name, rows in clients_map.items():
            chosen = _pick_preferred_contract_line(rows)
            upsert_client(
                name=client_name,
                business_type=chosen.get("business_type") or "",
                department=chosen.get("department") or "",
                entity=chosen.get("entity") or "",
                fee_clause=chosen.get("fee_clause") or "",
                payment_term=chosen.get("payment_term") or "",
                db=db,
            )

        db.commit()
        logger.info(
            "Feishu contract sync persisted %s line rows and aggregated %s clients",
            len(inserted_rows),
            len(clients_map),
        )
        return {
            "line_count": len(inserted_rows),
            "client_count": len(clients_map),
        }
    except OperationalError as exc:
        db.rollback()
        if "no such table: client_contract_lines" in str(exc).lower():
            raise RuntimeError("缺少表 client_contract_lines，请先执行 alembic upgrade head") from exc
        logger.exception("Database operation failed while migrating Feishu contract lines")
        raise
    except Exception:
        db.rollback()
        logger.exception("Failed to migrate Feishu contract lines")
        raise
    finally:
        db.close()


def _normalize_col(text: str) -> str:
    return str(text or "").strip().replace(" ", "").replace("_", "").lower()


def _find_column(columns: list[str], candidates: list[str]) -> str | None:
    normalized_map = {_normalize_col(col): col for col in columns}
    for candidate in candidates:
        key = _normalize_col(candidate)
        if key in normalized_map:
            return normalized_map[key]

    # Fuzzy fallback for Chinese labels
    for col in columns:
        ncol = _normalize_col(col)
        for candidate in candidates:
            nc = _normalize_col(candidate)
            if nc and nc in ncol:
                return col
    return None


def migrate_from_excel(excel_path: str | None = None) -> int:
    """从合同 Excel 迁移数据到 SQLite。"""
    if excel_path is None:
        excel_path = str(Path(__file__).parent.parent / "合同.xlsx")

    path = Path(excel_path)
    if not path.exists() or not path.is_file():
        raise ValueError(f"合同文件不存在: {excel_path}")

    try:
        df = pd.read_excel(path)
    except Exception as exc:
        raise ValueError(f"合同文件无法读取为 Excel: {exc}") from exc

    if df.empty:
        raise ValueError("合同模板为空，未读取到任何数据")

    columns = [str(col).strip() for col in df.columns]
    name_col = _find_column(columns, ["客户简称", "客户名称", "客户", "name", "client_name"])
    fee_col = _find_column(columns, ["服务费", "fee", "fee_clause"])

    if not name_col:
        raise ValueError("合同模板缺少必需列: 客户简称/客户名称")
    if not fee_col:
        raise ValueError("合同模板缺少必需列: 服务费")

    business_type_col = _find_column(columns, ["业务类型", "business_type"])
    department_col = _find_column(columns, ["执行部门", "department"])
    entity_col = _find_column(columns, ["客户主体", "entity"])

    data = []
    for _, row in df.iterrows():
        name = _to_text(row.get(name_col))
        if not name:
            continue

        data.append(
            {
                "name": name,
                "business_type": _to_text(row.get(business_type_col)) if business_type_col else None,
                "department": _to_text(row.get(department_col)) if department_col else None,
                "entity": _to_text(row.get(entity_col)) if entity_col else None,
                "fee_clause": _to_text(row.get(fee_col)),
            }
        )

    if not data:
        raise ValueError("合同模板未包含有效客户记录")

    count = migrate_client_data(data)
    logger.info("Contract migration completed. imported=%s", count)
    return count


if __name__ == "__main__":
    migrate_from_excel()
