from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from api.database import (
    record_operation_audit,
    replace_client_detail_stats_batch,
    replace_client_stats_batch,
    upsert_billing_history,
)
from api.models import BillingHistory, ClientMonthlyDetailStats, ClientMonthlyStats
from api.services.daily_fx_snapshot_service import DailyFxSnapshotService
from calculate_service_fee import calculate_service_fees

logger = logging.getLogger(__name__)


def secure_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal and unsafe chars."""
    if not filename:
        return "uploaded_file"
    filename = Path(filename).name
    filename = re.sub(r"[^\w.\-\u4e00-\u9fff]", "_", filename)
    if not filename or filename.strip() == ".":
        return "uploaded_file"
    return filename


class CalculationService:
    _MONTH_PATTERN = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")
    _RESULT_FILE_PATTERN = re.compile(r"^[\w.\-\u4e00-\u9fff]+_results\.xlsx$", re.IGNORECASE)
    _RESULT_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$", re.IGNORECASE)
    _ALLOWED_EXCEL_EXTENSIONS = {".xlsx", ".xls"}
    _TEXT_EMPTY_VALUES = {"", "-", "/", "—", "nan", "none"}
    _NET_CONSUMPTION_COLUMN_CANDIDATES = ("汇总纯花费", "汇总纯消耗")
    _COUPON_COLUMN_CANDIDATES = ("Coupon", "COUPON", "coupon")
    _DST_COLUMN_CANDIDATES = (
        "监管运营费用/数字服务税(DST)\xa0",
        "监管运营费用/数字服务税 (DST)\xa0",
        "监管运营费用/数字服务税(DST)",
        "监管运营费用/数字服务税 (DST)",
    )
    _DST_COLUMN_NORMALIZED = "监管运营费用/数字服务税(DST)"
    _DST_COLUMN_FUZZY_ALIASES = ("监管费", "监管运营费", "数字服务税", "dst")
    _HEADER_ALIASES: dict[str, tuple[str, ...]] = {
        "母公司": ("母公司 ",),
        "预付/后付": ("预付 / 后付", "预付后付", "预付/后付 "),
        "服务类型": ("服务类型 ",),
        "流水消耗": ("流水消耗 ",),
        "代投消耗": ("代投消耗 ",),
        "汇总纯花费": ("汇总纯消耗", "汇总纯花费 ", "汇总纯消耗 ", "汇总纯花费(USD)", "汇总纯消耗(USD)"),
        "换汇汇率": ("换汇汇率 ",),
        "服务费": ("服务费 ",),
        "固定服务费": ("固定服务费 ",),
        "Coupon": ("COUPON", "coupon", "Coupon "),
        "汇总": ("Summary", "合计", "总计", "汇总 "),
        "监管运营费用/数字服务税(DST)": _DST_COLUMN_CANDIDATES,
        "月份归属": ("月份归属 ",),
    }
    _NUMERIC_CANONICAL_COLUMNS = {
        "流水消耗",
        "代投消耗",
        "汇总纯花费",
        "换汇汇率",
        "服务费",
        "固定服务费",
        "Coupon",
        "汇总",
        "监管运营费用/数字服务税(DST)",
    }
    _DEFAULT_RESULT_OPERATIONS = {"calculate", "recalculate"}
    _ESTIMATE_RESULT_OPERATIONS = {"estimate_calculate", "estimate_recalculate"}
    _ESTIMATE_SHEET_NAME = "Sheet1"
    _ESTIMATE_OUTPUT_SHEET_NAME = "Sheet2"
    _RESULT_DATA_SHEET_NAME = "_CALC_DATA"
    _DASHBOARD_BACKFILL_SIGNATURE_FILE = ".dashboard_backfill_signature.json"
    _NET_CONSUMPTION_COLUMN_CANDIDATES = ("汇总纯花费", "汇总纯消耗", "账单汇总")
    _VISIBLE_CONSUMPTION_COLUMN_CANDIDATES = ("代投消耗", "流水消耗", "账单汇总", "代投/咨询拆分", "流水拆分")
    _CLIENT_ACCOUNT_SHEET_MARKERS = ("客户端口账户代投", "客户端口代投")
    _ESTIMATE_REQUIRED_COLUMNS = ("媒介", "投放类型", "母公司")

    def __init__(self, daily_fx_snapshot_service: DailyFxSnapshotService | None = None):
        self._daily_fx_snapshot_service = daily_fx_snapshot_service or DailyFxSnapshotService()
        self._result_registry_lock = threading.Lock()
        self._detail_backfill_lock = threading.Lock()
        self._detail_backfill_signature: tuple[tuple[str, int, int, str], ...] | None = None

    def _audit(
        self,
        *,
        action: str,
        actor: str,
        status: str,
        input_file: str | None = None,
        output_file: str | None = None,
        result_ref: str | None = None,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        record_operation_audit(
            category="billing",
            action=action,
            actor=actor,
            status=status,
            input_file=input_file,
            output_file=output_file,
            result_ref=result_ref,
            error_message=error_message,
            metadata=metadata,
        )

    def _get_upload_dir(self) -> Path:
        upload_dir = Path(__file__).parent.parent.parent / "uploads"
        upload_dir.mkdir(exist_ok=True)
        return upload_dir

    def _normalize_owner_key(self, owner_username: str | None) -> str:
        normalized = secure_filename(str(owner_username or "").strip().lower())
        if not normalized or normalized == "uploaded_file":
            return "system"
        return normalized

    def _build_upload_storage_filename(self, owner_username: str | None, original_filename: str) -> str:
        owner_key = self._normalize_owner_key(owner_username)
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
        unique = uuid.uuid4().hex[:8]
        safe_original = secure_filename(original_filename)
        return f"{owner_key}_{timestamp}_{unique}_{safe_original}"

    def _get_latest_consumption_meta_path(self, owner_username: str) -> Path:
        owner_key = self._normalize_owner_key(owner_username)
        return self._get_upload_dir() / f".latest_consumption_{owner_key}.json"

    def _get_latest_estimate_consumption_meta_path(self, owner_username: str) -> Path:
        owner_key = self._normalize_owner_key(owner_username)
        return self._get_upload_dir() / f".latest_estimate_consumption_{owner_key}.json"

    def _get_result_registry_path(self) -> Path:
        return self._get_upload_dir() / ".result_registry.json"

    def _validate_excel_extension(self, filename: str, *, context: str) -> None:
        suffix = Path(str(filename or "")).suffix.lower()
        if suffix not in self._ALLOWED_EXCEL_EXTENSIONS:
            allowed = ", ".join(sorted(self._ALLOWED_EXCEL_EXTENSIONS))
            raise HTTPException(status_code=400, detail=f"{context}仅支持 {allowed} 文件")

    def _open_excel_workbook(self, file_path: str, *, context: str) -> pd.ExcelFile:
        try:
            return pd.ExcelFile(file_path)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{context}无法读取为 Excel: {exc}") from exc

    def _extract_client_account_month(self, column_name) -> str | None:
        text = str(column_name or "").strip()
        if not text or "消耗" not in text:
            return None
        return self._parse_month_from_filename(text)

    def _is_client_account_sheet_name(self, sheet_name: str) -> bool:
        text = str(sheet_name or "")
        return any(marker in text for marker in self._CLIENT_ACCOUNT_SHEET_MARKERS)

    def _is_client_account_managed_sheet(self, sheet_name: str, columns: list[str] | set[str]) -> bool:
        if not self._is_client_account_sheet_name(sheet_name):
            return False

        column_list = [str(column).strip() for column in columns]
        column_set = set(column_list)
        if not {"母公司", "媒介"}.issubset(column_set):
            return False

        return any(self._extract_client_account_month(column_name) for column_name in column_list)

    def _find_client_account_month_column(self, columns: list[str] | set[str], target_month: str | None) -> str | None:
        if not target_month:
            return None

        for column_name in columns:
            if self._extract_client_account_month(column_name) == target_month:
                return str(column_name)
        return None

    def _validate_consumption_workbook(self, file_path: str, original_filename: str) -> None:
        workbook = self._open_excel_workbook(file_path, context="消耗上传文件")
        target_month = self._parse_month_from_filename(original_filename)
        try:
            valid_sheets = []
            missing_service_type = []
            missing_currency = []
            missing_target_month = []
            has_month_column = False
            has_consumption_column = False

            for sheet in workbook.sheet_names:
                header_df = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
                columns = [str(col).strip() for col in header_df.columns.tolist()]
                cols = set(columns)
                if any(candidate in cols for candidate in self._VISIBLE_CONSUMPTION_COLUMN_CANDIDATES):
                    has_consumption_column = True
                if not {"母公司", "媒介"}.issubset(cols):
                    continue

                if self._is_client_account_managed_sheet(sheet, columns):
                    valid_sheets.append(sheet)
                    has_consumption_column = True

                    if "币种" not in cols:
                        missing_currency.append(sheet)

                    month_column = self._find_client_account_month_column(columns, target_month)
                    if not target_month or not month_column:
                        missing_target_month.append(sheet)
                    continue

                if "服务类型" not in cols:
                    missing_service_type.append(sheet)
                    continue

                valid_sheets.append(sheet)
                if "月份归属" in cols:
                    has_month_column = True
                if "代投消耗" in cols or "流水消耗" in cols:
                    has_consumption_column = True

                sheet_currency = self._normalize_sheet_currency(sheet)
                if sheet_currency == "OTHER" and "币种" not in cols:
                    missing_currency.append(sheet)
                if sheet_currency is None and "币种" not in cols:
                    missing_currency.append(sheet)

            if missing_service_type:
                hint = "、".join(missing_service_type[:3])
                raise HTTPException(status_code=400, detail=f"模板缺少必需列“服务类型”，问题 Sheet: {hint}")

            if missing_currency:
                hint = "、".join(missing_currency[:3])
                raise HTTPException(status_code=400, detail=f"模板缺少必需列“币种”，问题 Sheet: {hint}")

            if missing_target_month:
                hint = "、".join(missing_target_month[:3])
                if not target_month:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "文件名缺少月份，无法识别“客户端口账户代投”Sheet 的目标消耗列，"
                            f"请使用 YYYY-MM 或 YYYY年M月 命名，问题 Sheet: {hint}"
                        ),
                    )
                raise HTTPException(
                    status_code=400,
                    detail=f"“客户端口账户代投”Sheet 未找到与文件月份 {target_month} 匹配的消耗列，问题 Sheet: {hint}",
                )

            if not valid_sheets:
                raise HTTPException(
                    status_code=400,
                    detail="未找到有效消耗数据 Sheet（至少包含 母公司/媒介/服务类型 列，或有效的“客户端口账户代投”Sheet）",
                )

            if not has_consumption_column:
                raise HTTPException(status_code=400, detail="模板缺少“代投消耗”或“流水消耗”列")

            if not has_month_column and not self._parse_month_from_filename(original_filename):
                raise HTTPException(
                    status_code=400,
                    detail="缺少月份信息：请在文件名中携带 YYYY-MM，或在表格中提供“月份归属”列",
                )
        finally:
            workbook.close()

    def _find_estimate_dynamic_column(
        self,
        columns: list[str],
        *,
        include_words: tuple[str, ...],
    ) -> str | None:
        for column_name in columns:
            text = str(column_name).strip()
            if text and all(word in text for word in include_words):
                return text
        return None

    def _normalize_estimate_text(self, value: Any) -> str:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass
        return str(value).strip()

    def _normalize_estimate_service_type(self, value: Any) -> str:
        text = self._normalize_estimate_text(value)
        if not text:
            return ""
        normalized = text.replace(" ", "")
        if "代投" in normalized and "流水" in normalized:
            return "代投+流水"
        if "代投" in normalized:
            return "代投"
        if "流水" in normalized:
            return "流水"
        return text

    def _resolve_estimate_sheet_name(self, workbook: pd.ExcelFile) -> str:
        preferred_sheet_names: list[str] = []
        if self._ESTIMATE_SHEET_NAME in workbook.sheet_names:
            preferred_sheet_names.append(self._ESTIMATE_SHEET_NAME)
        preferred_sheet_names.extend(
            sheet_name for sheet_name in workbook.sheet_names if sheet_name != self._ESTIMATE_SHEET_NAME
        )

        for sheet_name in preferred_sheet_names:
            header_df = pd.read_excel(workbook, sheet_name=sheet_name, nrows=0)
            columns = [str(col).strip() for col in header_df.columns.tolist()]
            if not set(self._ESTIMATE_REQUIRED_COLUMNS).issubset(set(columns)):
                continue

            consumption_col = self._find_estimate_dynamic_column(
                columns,
                include_words=("\u6d88\u8017", "\u9884\u4f30"),
            )
            gross_profit_col = self._find_estimate_dynamic_column(
                columns,
                include_words=("\u6bdb\u5229", "\u9884\u4f30"),
            )
            if consumption_col and gross_profit_col:
                return sheet_name

        raise HTTPException(
            status_code=400,
            detail="\u9884\u4f30\u6a21\u677f\u7f3a\u5c11\u53ef\u8bc6\u522b\u7684\u5de5\u4f5c\u8868\uff0c\u8bf7\u68c0\u67e5\u5fc5\u586b\u5217\u4e0e\u201c\u6d88\u8017\u9884\u4f30\u201d/\u201c\u6bdb\u5229\u9884\u4f30\u201d\u52a8\u6001\u5217",
        )

    def _validate_estimate_workbook(self, file_path: str) -> None:
        workbook = self._open_excel_workbook(file_path, context="\u9884\u4f30\u6a21\u677f\u4e0a\u4f20\u6587\u4ef6")
        try:
            self._resolve_estimate_sheet_name(workbook)
        finally:
            workbook.close()

    def _prepare_estimate_calculation_input(
        self,
        file_path: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, str, str, str]:
        workbook = self._open_excel_workbook(file_path, context="\u9884\u4f30\u6a21\u677f\u4e0a\u4f20\u6587\u4ef6")
        try:
            estimate_sheet_name = self._resolve_estimate_sheet_name(workbook)
        finally:
            workbook.close()

        source_sheet_df = pd.read_excel(file_path, sheet_name=estimate_sheet_name)
        column_lookup = {str(col).strip(): col for col in source_sheet_df.columns.tolist()}
        missing_columns = [col for col in self._ESTIMATE_REQUIRED_COLUMNS if col not in column_lookup]
        if missing_columns:
            raise HTTPException(
                status_code=400,
                detail=f"\u9884\u4f30\u6a21\u677f\u5de5\u4f5c\u8868 {estimate_sheet_name} \u7f3a\u5c11\u5fc5\u9700\u5217\uff1a{'\u3001'.join(missing_columns)}",
            )

        normalized_columns = list(column_lookup.keys())
        consumption_column_name = self._find_estimate_dynamic_column(
            normalized_columns,
            include_words=("\u6d88\u8017", "\u9884\u4f30"),
        )
        gross_profit_column_name = self._find_estimate_dynamic_column(
            normalized_columns,
            include_words=("\u6bdb\u5229", "\u9884\u4f30"),
        )
        if not consumption_column_name:
            raise HTTPException(
                status_code=400,
                detail=f"\u9884\u4f30\u6a21\u677f\u5de5\u4f5c\u8868 {estimate_sheet_name} \u7f3a\u5c11\u201c\u6d88\u8017\u9884\u4f30\u201d\u52a8\u6001\u5217",
            )
        if not gross_profit_column_name:
            raise HTTPException(
                status_code=400,
                detail=f"\u9884\u4f30\u6a21\u677f\u5de5\u4f5c\u8868 {estimate_sheet_name} \u7f3a\u5c11\u201c\u6bdb\u5229\u9884\u4f30\u201d\u52a8\u6001\u5217",
            )

        rows = pd.DataFrame(
            {
                "_source_client": source_sheet_df[column_lookup["\u6bcd\u516c\u53f8"]].map(self._normalize_estimate_text),
                "_service_type": source_sheet_df[column_lookup["\u6295\u653e\u7c7b\u578b"]].map(self._normalize_estimate_service_type),
                "\u5a92\u4ecb": source_sheet_df[column_lookup["\u5a92\u4ecb"]].map(self._normalize_estimate_text),
                "_estimate_consumption": pd.to_numeric(
                    source_sheet_df[column_lookup[consumption_column_name]],
                    errors="coerce",
                ).fillna(0.0),
                "_estimate_gross_profit": pd.to_numeric(
                    source_sheet_df[column_lookup[gross_profit_column_name]],
                    errors="coerce",
                ).fillna(0.0),
            }
        )
        rows = rows[
            (rows["_source_client"] != "")
            & (rows["_service_type"] != "")
            & (rows["\u5a92\u4ecb"] != "")
        ].copy()
        if rows.empty:
            raise HTTPException(
                status_code=400,
                detail=f"\u9884\u4f30\u6a21\u677f\u5de5\u4f5c\u8868 {estimate_sheet_name} \u6ca1\u6709\u53ef\u8ba1\u7b97\u7684\u6570\u636e\u884c",
            )

        from billing.contract_loader import load_contract_terms_from_db

        contract_terms = load_contract_terms_from_db()
        contract_name_map: dict[str, str] = {}
        for name in contract_terms:
            normalized_name = self._normalize_estimate_text(name)
            if normalized_name:
                contract_name_map.setdefault(normalized_name.lower(), normalized_name)

        def _resolve_contract_client_name(client_name: str) -> str:
            if not client_name:
                return client_name
            if client_name in contract_terms:
                return client_name
            return contract_name_map.get(client_name.lower(), client_name)

        rows["_contract_client"] = rows["_source_client"].apply(_resolve_contract_client_name)

        grouped = (
            rows.groupby(
                ["_source_client", "_service_type", "\u5a92\u4ecb", "_contract_client"],
                as_index=False,
            )[["_estimate_consumption", "_estimate_gross_profit"]]
            .sum()
        )

        sheet2_seed_df = grouped.rename(
            columns={
                "_source_client": "\u6bcd\u516c\u53f8",
                "_service_type": "\u670d\u52a1\u7c7b\u578b",
            }
        )

        calc_input_df = sheet2_seed_df[["_contract_client", "\u670d\u52a1\u7c7b\u578b", "\u5a92\u4ecb", "_estimate_consumption"]].copy()
        calc_input_df.rename(columns={"_contract_client": "\u6bcd\u516c\u53f8"}, inplace=True)
        calc_input_df["\u4ee3\u6295\u6d88\u8017"] = 0.0
        calc_input_df["\u6d41\u6c34\u6d88\u8017"] = 0.0
        calc_input_df.loc[
            calc_input_df["\u670d\u52a1\u7c7b\u578b"] == "\u4ee3\u6295",
            "\u4ee3\u6295\u6d88\u8017",
        ] = calc_input_df["_estimate_consumption"]
        calc_input_df.loc[
            calc_input_df["\u670d\u52a1\u7c7b\u578b"] == "\u6d41\u6c34",
            "\u6d41\u6c34\u6d88\u8017",
        ] = calc_input_df["_estimate_consumption"]
        calc_input_df = calc_input_df[
            ["\u6bcd\u516c\u53f8", "\u5a92\u4ecb", "\u670d\u52a1\u7c7b\u578b", "\u4ee3\u6295\u6d88\u8017", "\u6d41\u6c34\u6d88\u8017"]
        ]

        return (
            source_sheet_df,
            sheet2_seed_df,
            calc_input_df,
            consumption_column_name,
            gross_profit_column_name,
            estimate_sheet_name,
        )

    def _build_estimate_sheet2_output(
        self,
        *,
        sheet2_seed_df: pd.DataFrame,
        result_df: pd.DataFrame,
        consumption_column_name: str,
        gross_profit_column_name: str,
    ) -> pd.DataFrame:
        if {"母公司", "服务类型", "媒介"}.issubset(set(result_df.columns.tolist())):
            fee_df = result_df[["母公司", "服务类型", "媒介"]].copy()
            fee_df["服务费"] = pd.to_numeric(result_df.get("服务费"), errors="coerce").fillna(0.0)
            fee_df["固定服务费"] = pd.to_numeric(result_df.get("固定服务费"), errors="coerce").fillna(0.0)
            fee_df = (
                fee_df.groupby(["母公司", "服务类型", "媒介"], as_index=False)[["服务费", "固定服务费"]]
                .sum()
                .rename(
                    columns={
                        "母公司": "_contract_client",
                        "服务费": "_estimate_service_fee",
                        "固定服务费": "_estimate_fixed_service_fee",
                    }
                )
            )
        else:
            fee_df = pd.DataFrame(
                columns=[
                    "_contract_client",
                    "服务类型",
                    "媒介",
                    "_estimate_service_fee",
                    "_estimate_fixed_service_fee",
                ]
            )

        merged = sheet2_seed_df.merge(
            fee_df,
            how="left",
            on=["_contract_client", "服务类型", "媒介"],
        )
        merged["_estimate_service_fee"] = pd.to_numeric(
            merged.get("_estimate_service_fee"),
            errors="coerce",
        ).fillna(0.0)
        merged["_estimate_fixed_service_fee"] = pd.to_numeric(
            merged.get("_estimate_fixed_service_fee"),
            errors="coerce",
        ).fillna(0.0)

        merged["_estimate_service_fee"] = pd.to_numeric(
            merged.get("_estimate_service_fee"),
            errors="coerce",
        ).fillna(0.0)
        merged["_estimate_fixed_service_fee"] = pd.to_numeric(
            merged.get("_estimate_fixed_service_fee"),
            errors="coerce",
        ).fillna(0.0)

        # 预估消耗为 0 时：按母公司汇总，如果该客户当月总预估消耗为 0，则预估服务费/固定服务费皆为 0
        client_totals = merged.groupby("_contract_client")["_estimate_consumption"].sum()
        zero_clients = client_totals[client_totals.abs() < 1e-9].index
        
        zero_mask = merged["_contract_client"].isin(zero_clients)
        merged.loc[zero_mask, "_estimate_service_fee"] = 0.0
        merged.loc[zero_mask, "_estimate_fixed_service_fee"] = 0.0

        # 新增判断：如果该客户本月「完全没有」涉及“代投”的任何行，也抹除固定服务费
        daitou_mask = merged["服务类型"].str.contains("代投", na=False)
        daitou_clients = merged.loc[daitou_mask, "_contract_client"].unique()
        no_daitou_mask = ~merged["_contract_client"].isin(daitou_clients)
        merged.loc[no_daitou_mask, "_estimate_fixed_service_fee"] = 0.0

        # （不再在结果构建层按行粗暴抹除固费，避免误删引擎层面已经去重后恰好赋给了某个流水行的全局固定费）

        return pd.DataFrame(
            {
                "母公司": merged["母公司"],
                "服务类型": merged["服务类型"],
                "媒介": merged["媒介"],
                consumption_column_name: merged["_estimate_consumption"],
                "预估服务费": merged["_estimate_service_fee"],
                "预估固定服务费": merged["_estimate_fixed_service_fee"],
                gross_profit_column_name: merged["_estimate_gross_profit"],
            }
        )

    def _validate_contract_workbook(self, file_path: str) -> None:
        workbook = self._open_excel_workbook(file_path, context="合同上传文件")
        try:
            if not workbook.sheet_names:
                raise HTTPException(status_code=400, detail="合同模板为空，未检测到任何 Sheet")

            sample_df = pd.read_excel(workbook, sheet_name=workbook.sheet_names[0], nrows=0)
            columns = [str(col).strip() for col in sample_df.columns]
            normalized = [col.replace(" ", "").lower() for col in columns]

            has_client_col = any(
                ("客户" in col and ("简称" in col or "名称" in col)) or col in {"name", "client"}
                for col in normalized
            )
            has_fee_col = any(("服务费" in col) or ("fee" in col) for col in normalized)

            if not has_client_col:
                raise HTTPException(status_code=400, detail="合同模板缺少必需列：客户简称/客户名称")
            if not has_fee_col:
                raise HTTPException(status_code=400, detail="合同模板缺少必需列：服务费")
        finally:
            workbook.close()

    def _default_result_registry(self) -> dict[str, Any]:
        return {"records": []}

    def _load_result_registry_unlocked(self) -> dict[str, Any]:
        path = self._get_result_registry_path()
        if not path.exists():
            return self._default_result_registry()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("读取结果注册表失败，回退为空", exc_info=True)
            return self._default_result_registry()

        records = payload.get("records", []) if isinstance(payload, dict) else []
        normalized_records = []
        for item in records:
            if not isinstance(item, dict):
                continue
            result_id = str(item.get("id") or "").strip().lower()
            owner = str(item.get("owner") or "").strip()
            filename = secure_filename(str(item.get("filename") or ""))
            if not self._RESULT_ID_PATTERN.match(result_id):
                continue
            if not owner or not self._is_allowed_result_filename(filename):
                continue
            normalized_records.append(
                {
                    "id": result_id,
                    "owner": owner,
                    "filename": filename,
                    "source_file": str(item.get("source_file") or ""),
                    "operation": str(item.get("operation") or "calculate"),
                    "created_at": str(item.get("created_at") or datetime.utcnow().isoformat()),
                }
            )
        return {"records": normalized_records}

    def _save_result_registry_unlocked(self, state: dict[str, Any]) -> None:
        path = self._get_result_registry_path()
        tmp_path = path.with_suffix(f"{path.suffix}.{uuid.uuid4().hex}.tmp")
        serialized = json.dumps(state, ensure_ascii=False, indent=2)
        tmp_path.write_text(serialized, encoding="utf-8")
        try:
            tmp_path.replace(path)
            return
        except PermissionError:
            logger.warning("Atomic replace for result registry failed, fallback to direct write", exc_info=True)
        try:
            path.write_text(serialized, encoding="utf-8")
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink(missing_ok=True)
                except PermissionError:
                    logger.warning("Failed to cleanup result registry temp file: %s", tmp_path, exc_info=True)

    def _prune_result_records(self, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        pruned = []
        upload_dir = self._get_upload_dir()
        for record in records:
            filename = secure_filename(str(record.get("filename") or ""))
            if not self._is_allowed_result_filename(filename):
                continue
            file_path = upload_dir / filename
            if file_path.exists() and file_path.is_file():
                pruned.append(record)
        return pruned[-1000:]

    def _register_result(
        self,
        *,
        filename: str,
        owner_username: str,
        source_file: str,
        operation: str,
    ) -> dict[str, Any]:
        record = {
            "id": uuid.uuid4().hex,
            "owner": owner_username,
            "filename": filename,
            "source_file": source_file,
            "operation": operation,
            "created_at": datetime.utcnow().isoformat(),
        }
        with self._result_registry_lock:
            state = self._load_result_registry_unlocked()
            records = self._prune_result_records(state.get("records", []))
            records.append(record)
            state["records"] = records[-1000:]
            self._save_result_registry_unlocked(state)
        return record

    def _resolve_result_record_for_user(self, result_ref: str, owner_username: str) -> dict[str, Any]:
        normalized_ref = str(result_ref or "").strip()
        if not normalized_ref:
            raise HTTPException(status_code=400, detail="结果标识不能为空")

        with self._result_registry_lock:
            state = self._load_result_registry_unlocked()
            records = self._prune_result_records(state.get("records", []))
            state["records"] = records
            self._save_result_registry_unlocked(state)

        # Preferred: result_id lookup
        if self._RESULT_ID_PATTERN.match(normalized_ref):
            any_match = [item for item in records if item["id"] == normalized_ref.lower()]
            if not any_match:
                raise HTTPException(status_code=404, detail="结果不存在或已过期")
            owned = [item for item in any_match if item["owner"] == owner_username]
            if not owned:
                raise HTTPException(status_code=403, detail="无权访问该结果")
            return owned[-1]

        # Backward compatibility: allow filename if and only if owned by user.
        safe_filename = secure_filename(normalized_ref)
        if not self._is_allowed_result_filename(safe_filename):
            raise HTTPException(status_code=400, detail="非法结果标识")

        matched = [item for item in records if item["filename"] == safe_filename]
        if not matched:
            raise HTTPException(status_code=404, detail="结果不存在或已过期")
        owned = [item for item in matched if item["owner"] == owner_username]
        if not owned:
            raise HTTPException(status_code=403, detail="无权访问该结果")
        return owned[-1]

    def _is_allowed_result_filename(self, filename: str) -> bool:
        return bool(filename and self._RESULT_FILE_PATTERN.match(filename))

    def _resolve_result_file(self, filename: str) -> Path:
        safe_filename = secure_filename(filename)
        if not self._is_allowed_result_filename(safe_filename):
            raise HTTPException(status_code=400, detail="Invalid result filename")

        file_path = self._get_upload_dir() / safe_filename
        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail=f"文件不存在: {safe_filename}")
        return file_path

    def _is_legacy_dashboard_result_filename(self, filename: str) -> bool:
        normalized = str(filename or "").strip().lower()
        if "estimate_results" in normalized:
            return False
        if "recalc_input_results" in normalized:
            return False
        return self._is_allowed_result_filename(secure_filename(filename))

    def _get_dashboard_result_entries(self) -> list[dict[str, Any]]:
        upload_dir = self._get_upload_dir()
        with self._result_registry_lock:
            state = self._load_result_registry_unlocked()
            records = self._prune_result_records(state.get("records", []))
            state["records"] = records
            self._save_result_registry_unlocked(state)

        latest_record_by_filename: dict[str, dict[str, Any]] = {}
        for record in records:
            operation = str(record.get("operation") or "calculate").strip() or "calculate"
            if operation not in self._DEFAULT_RESULT_OPERATIONS:
                continue

            filename = secure_filename(str(record.get("filename") or ""))
            if not filename:
                continue

            file_path = upload_dir / filename
            if not file_path.exists() or not file_path.is_file():
                continue

            latest_record_by_filename[filename] = {
                "filename": filename,
                "path": file_path,
                "source_file": str(record.get("source_file") or ""),
                "created_at": str(record.get("created_at") or ""),
            }

        if latest_record_by_filename:
            return sorted(
                latest_record_by_filename.values(),
                key=lambda item: (str(item.get("created_at") or ""), str(item.get("filename") or "")),
            )

        legacy_entries: list[dict[str, Any]] = []
        for path in sorted(
            upload_dir.glob("*_results.xlsx"),
            key=lambda item: (item.stat().st_mtime_ns, item.name),
        ):
            if not self._is_legacy_dashboard_result_filename(path.name):
                continue
            legacy_entries.append(
                {
                    "filename": path.name,
                    "path": path,
                    "source_file": "",
                    "created_at": "",
                }
            )
        return legacy_entries

    def list_result_files(self) -> list[Path]:
        upload_dir = self._get_upload_dir()
        return [path for path in upload_dir.glob("*_results.xlsx") if self._is_allowed_result_filename(path.name)]

    def get_latest_result_info(self) -> dict:
        result_files = self.list_result_files()
        if not result_files:
            return {"has_result": False}

        latest = max(result_files, key=lambda f: f.stat().st_mtime)
        filename = latest.name
        return {
            "has_result": True,
            "filename": filename,
            "data_url": f"/api/results/{filename}",
            "download_url": f"/api/download/{filename}",
        }

    def get_latest_result_info_for_user(
        self,
        owner_username: str,
        *,
        operations: set[str] | None = None,
    ) -> dict[str, Any]:
        with self._result_registry_lock:
            state = self._load_result_registry_unlocked()
            records = self._prune_result_records(state.get("records", []))
            state["records"] = records
            self._save_result_registry_unlocked(state)

        user_records = [item for item in records if item.get("owner") == owner_username]
        if operations:
            user_records = [
                item
                for item in user_records
                if str(item.get("operation") or "").strip() in operations
            ]
        if not user_records:
            return {"has_result": False}

        latest = max(user_records, key=lambda item: str(item.get("created_at") or ""))
        result_id = str(latest["id"])
        filename = str(latest["filename"])
        return {
            "has_result": True,
            "result_id": result_id,
            "filename": filename,
            "output_file": filename,
            "data_url": f"/api/results/{result_id}",
            "download_url": f"/api/download/{result_id}",
            "created_at": latest.get("created_at", ""),
            "source_file": latest.get("source_file", ""),
            "operation": latest.get("operation", ""),
        }
    def _normalize_sheet_currency(self, sheet_name: str) -> str | None:
        name = str(sheet_name or "").strip().lower().replace(" ", "")
        if any(x in name for x in ("jpy", "日元", "日币")):
            return "JPY"
        if any(x in name for x in ("eur", "欧元")):
            return "EUR"
        if any(x in name for x in ("rmb", "cny", "人民币")):
            return "RMB"
        if any(x in name for x in ("usd", "美元", "美金", "us$")):
            return "USD"
        if "其他" in name:
            return "OTHER"
        return None

    def _normalize_currency_value(self, value) -> str:
        text = str(value or "").strip().upper()
        if text in {"CNY", "RMB", "人民币", "RENMINBI"}:
            return "RMB"
        if text in {"EUR", "欧元"}:
            return "EUR"
        if text in {"JPY", "日元", "日币"}:
            return "JPY"
        if text in {"USD", "美元", "美金"}:
            return "USD"
        return text

    def _match_currency_hint(self, value) -> str:
        text = str(value or "").strip().upper().replace(" ", "")
        if not text:
            return ""
        if any(token in text for token in ("CNY", "RMB", "人民币", "RENMINBI")):
            return "RMB"
        if any(token in text for token in ("EUR", "欧元")):
            return "EUR"
        if any(token in text for token in ("JPY", "日元", "日币", "日圆")):
            return "JPY"
        if any(token in text for token in ("USD", "US$", "美元", "美金")):
            return "USD"
        return ""

    def _infer_client_account_currency(self, row: pd.Series) -> str:
        explicit_raw = row.get("币种")
        explicit_hint = self._match_currency_hint(explicit_raw)
        if explicit_hint:
            return explicit_hint

        explicit = self._normalize_currency_value(explicit_raw)
        if explicit:
            return explicit

        for column_name in ("渠道", "媒介", "母公司", "帐号 ID", "账号 ID", "账号ID"):
            hinted = self._match_currency_hint(row.get(column_name))
            if hinted:
                return hinted

        return "USD"

    def _contains_currency_consumption(
        self,
        file_path: str,
        target_currencies: set[str],
        *,
        month_hint: str | None = None,
    ) -> bool:
        workbook = self._open_excel_workbook(file_path, context="消耗上传文件")
        required_cols = {"母公司", "媒介", "服务类型"}
        normalized_targets = {self._normalize_currency_value(item) for item in target_currencies}
        try:
            for sheet in workbook.sheet_names:
                df = pd.read_excel(workbook, sheet_name=sheet)
                if df.empty:
                    continue

                columns = [str(col).strip() for col in df.columns.tolist()]
                cols = set(columns)
                if self._is_client_account_managed_sheet(sheet, columns):
                    if "币种" not in cols:
                        raise HTTPException(status_code=400, detail="‘客户端口账户代投’Sheet 缺少‘币种’列")
                    month_column = self._find_client_account_month_column(columns, month_hint)
                    if not month_column:
                        continue
                    currency_series = df.apply(self._infer_client_account_currency, axis=1)
                    consumption_series = pd.to_numeric(df[month_column], errors="coerce").fillna(0.0)
                    active_currency_series = currency_series[consumption_series.abs() > 1e-9]
                    if active_currency_series.isin(normalized_targets).any():
                        return True
                    continue

                if not required_cols.issubset(cols):
                    continue

                sheet_currency = self._normalize_sheet_currency(sheet)
                if sheet_currency and sheet_currency in normalized_targets:
                    return True
                if sheet_currency in {"USD", "RMB", "JPY", "EUR"}:
                    continue

                if "币种" not in cols:
                    if sheet_currency == "OTHER":
                        raise HTTPException(status_code=400, detail="‘其他币种’Sheet 缺少‘币种’列")
                    continue

                currency_series = df["币种"].apply(self._normalize_currency_value)
                if currency_series.isin(normalized_targets).any():
                    return True

            return False
        finally:
            workbook.close()

    def _contains_rmb_consumption(self, file_path: str, *, month_hint: str | None = None) -> bool:
        return self._contains_currency_consumption(file_path, {"RMB"}, month_hint=month_hint)

    def _contains_eur_consumption(self, file_path: str, *, month_hint: str | None = None) -> bool:
        return self._contains_currency_consumption(file_path, {"EUR"}, month_hint=month_hint)

    def _contains_jpy_consumption(self, file_path: str, *, month_hint: str | None = None) -> bool:
        return self._contains_currency_consumption(file_path, {"JPY"}, month_hint=month_hint)

    def _build_daily_exchange_context(self, require_snapshot: bool) -> dict:
        today_snapshot = self._daily_fx_snapshot_service.get_today_snapshot()
        if require_snapshot and not today_snapshot:
            raise HTTPException(
                status_code=400,
                detail=(
                    "检测到 RMB、EUR 或 JPY 消耗，但今日恒生汇率快照尚未生效。"
                    "请先前往“汇率监控”页面补录今日快照，再重新计算。"
                ),
            )
        return {"hangseng_today": today_snapshot or {}}

    def _record_latest_uploaded_file(
        self,
        file_path: str,
        original_filename: str | None,
        *,
        owner_username: str,
        estimate: bool = False,
    ) -> None:
        meta_path = (
            self._get_latest_estimate_consumption_meta_path(owner_username)
            if estimate
            else self._get_latest_consumption_meta_path(owner_username)
        )
        payload = {
            "file_path": str(Path(file_path).resolve()),
            "original_filename": original_filename or Path(file_path).name,
            "owner": self._normalize_owner_key(owner_username),
        }
        try:
            meta_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.warning("保存最近消耗文件元数据失败", exc_info=True)

    def _record_latest_consumption(
        self,
        file_path: str,
        original_filename: str | None,
        *,
        owner_username: str,
    ):
        self._record_latest_uploaded_file(
            file_path,
            original_filename,
            owner_username=owner_username,
            estimate=False,
        )

    def _record_latest_estimate_consumption(
        self,
        file_path: str,
        original_filename: str | None,
        *,
        owner_username: str,
    ):
        self._record_latest_uploaded_file(
            file_path,
            original_filename,
            owner_username=owner_username,
            estimate=True,
        )

    def _cleanup_failed_upload(self, file_path: Path) -> None:
        if not file_path.exists():
            return

        def _delayed_cleanup(target: Path) -> None:
            if not target.exists():
                return
            try:
                target.unlink(missing_ok=True)
                logger.info("延迟清理上传临时文件成功: %s", target)
            except PermissionError as exc:
                logger.warning("延迟清理上传临时文件失败: %s (%s)", target, exc)

        for attempt in range(3):
            try:
                file_path.unlink(missing_ok=True)
                return
            except PermissionError as exc:
                if attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                logger.warning("上传校验失败后清理文件被占用，保留临时文件: %s (%s)", file_path, exc)
                timer = threading.Timer(5.0, _delayed_cleanup, args=(file_path,))
                timer.daemon = True
                timer.start()

    def _looks_like_consumption_file(self, file_path: Path) -> bool:
        try:
            required_cols = {"母公司", "媒介", "服务类型"}
            workbook = self._open_excel_workbook(str(file_path), context="消耗上传文件")
            try:
                for sheet in workbook.sheet_names:
                    header_df = pd.read_excel(workbook, sheet_name=sheet, nrows=0)
                    columns = [str(col).strip() for col in header_df.columns.tolist()]
                    cols = set(columns)
                    if required_cols.issubset(cols) or self._is_client_account_managed_sheet(sheet, columns):
                        return True
                return False
            finally:
                workbook.close()
        except Exception:
            return False

    def _looks_like_estimate_consumption_file(self, file_path: Path) -> bool:
        try:
            workbook = pd.ExcelFile(file_path)
            try:
                self._resolve_estimate_sheet_name(workbook)
                return True
            finally:
                workbook.close()
        except Exception:
            return False

    def _get_latest_uploaded_file(
        self,
        *,
        owner_username: str,
        estimate: bool,
    ) -> tuple[str, str]:
        owner_key = self._normalize_owner_key(owner_username)
        meta_path = (
            self._get_latest_estimate_consumption_meta_path(owner_username)
            if estimate
            else self._get_latest_consumption_meta_path(owner_username)
        )
        looks_like = self._looks_like_estimate_consumption_file if estimate else self._looks_like_consumption_file
        not_found_message = (
            "未找到可重算的预估消耗文件，请先上传预估模板。"
            if estimate
            else "未找到可重算的消耗文件，请先上传消耗数据。"
        )
        if meta_path.exists():
            try:
                payload = json.loads(meta_path.read_text(encoding="utf-8"))
                candidate = Path(str(payload.get("file_path", "")).strip())
                original = str(payload.get("original_filename") or candidate.name)
                payload_owner = self._normalize_owner_key(payload.get("owner"))
                if (
                    payload_owner == owner_key
                    and candidate.exists()
                    and candidate.is_file()
                    and looks_like(candidate)
                ):
                    return str(candidate), original
            except Exception:
                logger.warning("读取最近上传文件元数据失败，改用目录扫描", exc_info=True)

        upload_dir = self._get_upload_dir()
        candidates = sorted(
            [
                p
                for p in upload_dir.iterdir()
                if p.is_file()
                and p.suffix.lower() in {".xlsx", ".xls"}
                and not p.name.startswith("~$")
                and "_results" not in p.stem.lower()
                and p.name.startswith(f"{owner_key}_")
            ],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for candidate in candidates:
            if looks_like(candidate):
                return str(candidate), candidate.name

        raise HTTPException(status_code=404, detail=not_found_message)

    def get_latest_consumption_file(self, owner_username: str = "system") -> tuple[str, str]:
        """Get latest uploaded consumption file path and original filename."""
        return self._get_latest_uploaded_file(owner_username=owner_username, estimate=False)

    def get_latest_estimate_consumption_file(self, owner_username: str = "system") -> tuple[str, str]:
        return self._get_latest_uploaded_file(owner_username=owner_username, estimate=True)

    def recalculate_latest(self, owner_username: str = "system"):
        """Re-run calculation with latest uploaded consumption file."""
        file_path, original_filename = self.get_latest_consumption_file(owner_username=owner_username)
        result = self.process_local_file(
            file_path,
            original_filename,
            owner_username=owner_username,
            operation="recalculate",
        )
        result["source_file"] = Path(file_path).name
        return result

    def recalculate_latest_estimate(self, owner_username: str = "system"):
        file_path, original_filename = self.get_latest_estimate_consumption_file(owner_username=owner_username)
        result = self.process_estimate_local_file(
            file_path,
            original_filename,
            owner_username=owner_username,
            operation="estimate_recalculate",
        )
        result["source_file"] = Path(file_path).name
        return result

    async def save_uploaded_file(self, file: UploadFile, owner_username: str = "system") -> str:
        """Save uploaded file to disk and return the local path."""
        upload_dir = self._get_upload_dir()
        safe_filename = secure_filename(file.filename)
        self._validate_excel_extension(safe_filename, context="消耗上传文件")
        stored_filename = self._build_upload_storage_filename(owner_username, safe_filename)
        file_path = upload_dir / stored_filename

        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            self._validate_consumption_workbook(str(file_path), file.filename or safe_filename)
            self._record_latest_consumption(
                str(file_path),
                file.filename,
                owner_username=owner_username,
            )
            self._audit(
                action="upload_consumption",
                actor=owner_username,
                status="success",
                input_file=safe_filename,
            )
            return str(file_path)
        except HTTPException as exc:
            self._cleanup_failed_upload(file_path)
            self._audit(
                action="upload_consumption",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc.detail),
            )
            raise
        except Exception as exc:
            logger.error("File save failed for %s", safe_filename, exc_info=True)
            self._audit(
                action="upload_consumption",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=500, detail=f"File save failed: {exc}")

    async def save_uploaded_estimate_file(self, file: UploadFile, owner_username: str = "system") -> str:
        upload_dir = self._get_upload_dir()
        safe_filename = secure_filename(file.filename)
        self._validate_excel_extension(safe_filename, context="预估模板上传文件")
        stored_filename = self._build_upload_storage_filename(owner_username, safe_filename)
        file_path = upload_dir / stored_filename

        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            self._validate_estimate_workbook(str(file_path))
            self._record_latest_estimate_consumption(
                str(file_path),
                file.filename,
                owner_username=owner_username,
            )
            self._audit(
                action="upload_estimate_consumption",
                actor=owner_username,
                status="success",
                input_file=safe_filename,
            )
            return str(file_path)
        except HTTPException as exc:
            self._cleanup_failed_upload(file_path)
            self._audit(
                action="upload_estimate_consumption",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc.detail),
            )
            raise
        except Exception as exc:
            logger.error("Estimate file save failed for %s", safe_filename, exc_info=True)
            self._audit(
                action="upload_estimate_consumption",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=500, detail=f"Estimate file save failed: {exc}")

    async def process_calculation(self, file: UploadFile, owner_username: str = "system"):
        file_path = await self.save_uploaded_file(file, owner_username=owner_username)
        return self.process_local_file(
            file_path,
            file.filename or Path(file_path).name,
            owner_username=owner_username,
            operation="calculate",
        )

    async def process_estimate_calculation(self, file: UploadFile, owner_username: str = "system"):
        file_path = await self.save_uploaded_estimate_file(file, owner_username=owner_username)
        return self.process_estimate_local_file(
            file_path,
            file.filename or Path(file_path).name,
            owner_username=owner_username,
            operation="estimate_calculate",
        )

    def _run_calculation_core(
        self,
        file_path: str,
        original_filename: str,
        *,
        persist_stats: bool,
        require_fx_snapshot: bool,
        exchange_context: dict[str, Any] | None = None,
        output_path: str | None = None,
    ) -> str:
        month_hint = self._parse_month_from_filename(original_filename)
        calculation_date = month_hint or None

        if exchange_context is None:
            if require_fx_snapshot:
                has_rmb_rows = self._contains_rmb_consumption(file_path, month_hint=month_hint)
                has_eur_rows = self._contains_eur_consumption(file_path, month_hint=month_hint)
                has_jpy_rows = self._contains_jpy_consumption(file_path, month_hint=month_hint)
                exchange_context = self._build_daily_exchange_context(
                    require_snapshot=has_rmb_rows or has_eur_rows or has_jpy_rows
                )
            else:
                exchange_context = {"hangseng_today": {}}

        output_file = calculate_service_fees(
            file_path,
            contract_path=None,
            output_path=output_path,
            use_db=True,
            calculation_date=calculation_date,
            exchange_context=exchange_context,
        )

        if persist_stats:
            self._update_stats_from_result(original_filename, output_file)
        return output_file

    def process_local_file(
        self,
        file_path: str,
        original_filename: str,
        *,
        owner_username: str = "system",
        operation: str = "calculate",
        persist_stats: bool = True,
        require_fx_snapshot: bool = True,
        exchange_context: dict[str, Any] | None = None,
        output_path: str | None = None,
    ):
        """Run the core billing calculation and update statistics."""
        try:
            output_file = self._run_calculation_core(
                file_path,
                original_filename,
                persist_stats=persist_stats,
                require_fx_snapshot=require_fx_snapshot,
                exchange_context=exchange_context,
                output_path=output_path,
            )

            output_name = Path(output_file).name
            result_record = self._register_result(
                filename=output_name,
                owner_username=owner_username,
                source_file=original_filename,
                operation=operation,
            )
            result_id = str(result_record["id"])
            self._audit(
                action=operation,
                actor=owner_username,
                status="success",
                input_file=original_filename,
                output_file=output_name,
                result_ref=result_id,
            )
            return {
                "status": "ok",
                "result_id": result_id,
                "output_file": output_name,
                "download_url": f"/api/download/{result_id}",
                "data_url": f"/api/results/{result_id}",
            }
        except HTTPException as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc.detail),
            )
            raise
        except ValueError as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc),
            )
            logger.error("Local file processing failed", exc_info=True)
            raise

    def process_estimate_local_file(
        self,
        file_path: str,
        original_filename: str,
        *,
        owner_username: str = "system",
        operation: str = "estimate_calculate",
    ) -> dict[str, Any]:
        temp_input: Path | None = None
        temp_output: Path | None = None
        try:
            (
                sheet1_df,
                sheet2_seed_df,
                calc_input_df,
                consumption_column_name,
                gross_profit_column_name,
                estimate_sheet_name,
            ) = self._prepare_estimate_calculation_input(file_path)
            upload_dir = self._get_upload_dir()
            temp_id = uuid.uuid4().hex
            temp_input = upload_dir / f"estimate_calc_input_{temp_id}.xlsx"
            temp_output = upload_dir / f"estimate_calc_output_{temp_id}.xlsx"

            calc_input_df.to_excel(temp_input, index=False, sheet_name="USD")
            output_file = self._run_calculation_core(
                str(temp_input),
                original_filename,
                persist_stats=False,
                require_fx_snapshot=False,
                exchange_context={"hangseng_today": {}},
                output_path=str(temp_output),
            )

            result_df = pd.read_excel(output_file)
            sheet2_df = self._build_estimate_sheet2_output(
                sheet2_seed_df=sheet2_seed_df,
                result_df=result_df,
                consumption_column_name=consumption_column_name,
                gross_profit_column_name=gross_profit_column_name,
            )

            original_path = Path(original_filename)
            if original_path.suffix.lower() in self._ALLOWED_EXCEL_EXTENSIONS:
                output_name = f"{original_path.stem}_estimate_results{original_path.suffix}"
            else:
                output_name = f"{original_path.stem}_estimate_results.xlsx"
            final_output_path = upload_dir / secure_filename(output_name)
            output_sheet2_name = self._ESTIMATE_OUTPUT_SHEET_NAME
            if estimate_sheet_name == output_sheet2_name:
                output_sheet2_name = f"{self._ESTIMATE_OUTPUT_SHEET_NAME}_RESULT"

            with pd.ExcelWriter(final_output_path) as writer:
                sheet1_df.to_excel(writer, index=False, sheet_name=estimate_sheet_name)
                sheet2_df.to_excel(writer, index=False, sheet_name=output_sheet2_name)

            result_record = self._register_result(
                filename=final_output_path.name,
                owner_username=owner_username,
                source_file=original_filename,
                operation=operation,
            )
            result_id = str(result_record["id"])
            self._audit(
                action=operation,
                actor=owner_username,
                status="success",
                input_file=original_filename,
                output_file=final_output_path.name,
                result_ref=result_id,
            )
            return {
                "status": "ok",
                "result_id": result_id,
                "output_file": final_output_path.name,
                "download_url": f"/api/download/{result_id}",
                "data_url": f"/api/results/{result_id}",
            }
        except HTTPException as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc.detail),
            )
            raise
        except ValueError as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            self._audit(
                action=operation,
                actor=owner_username,
                status="failed",
                input_file=original_filename,
                error_message=str(exc),
            )
            logger.error("Estimate local file processing failed", exc_info=True)
            raise
        finally:
            for temp_path in (temp_input, temp_output):
                if temp_path and temp_path.exists():
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        logger.warning("Failed to cleanup temp estimate file: %s", temp_path, exc_info=True)

    def _is_valid_month_string(self, month_text: str) -> bool:
        return bool(month_text and self._MONTH_PATTERN.match(month_text))

    def _normalize_month_value(self, raw_value) -> str | None:
        if pd.isna(raw_value):
            return None

        def _fmt_month(year: int, month: int) -> str | None:
            if 2000 <= year <= 2099 and 1 <= month <= 12:
                return f"{year}-{month:02d}"
            return None

        if isinstance(raw_value, (pd.Timestamp, datetime, date)):
            return _fmt_month(int(raw_value.year), int(raw_value.month))

        numeric_value = None
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            numeric_value = float(raw_value)
        elif isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return None

            compact_match = re.search(r"(20\d{2})\s*[年/\-_]?\s*(\d{1,2})\s*月?", text)
            if compact_match:
                return _fmt_month(int(compact_match.group(1)), int(compact_match.group(2)))

            if re.fullmatch(r"\d+(?:\.\d+)?", text):
                numeric_value = float(text)
            else:
                dt = pd.to_datetime(text, errors="coerce")
                if pd.notna(dt):
                    return _fmt_month(int(dt.year), int(dt.month))
                return None

        if numeric_value is None:
            return None

        rounded = int(round(numeric_value))
        if abs(numeric_value - rounded) < 1e-9:
            if 200001 <= rounded <= 209912:
                return _fmt_month(rounded // 100, rounded % 100)

            if 30000 <= rounded <= 70000:
                excel_dt = pd.to_datetime(rounded, unit="D", origin="1899-12-30", errors="coerce")
                if pd.notna(excel_dt):
                    return _fmt_month(int(excel_dt.year), int(excel_dt.month))

        dt = pd.to_datetime(numeric_value, errors="coerce")
        if pd.notna(dt):
            return _fmt_month(int(dt.year), int(dt.month))
        return None

    def _parse_month_from_filename(self, filename: str, *, prefer_latest_match: bool = False) -> str | None:
        patterns = [
            r"(\d{4})[._\-\s]?(\d{1,2})",  # 2024.01 / 2024-01 / 2024 01
            r"(\d{4})年\s*(\d{1,2})月",      # 2024年1月
            r"(20\d{2})(\d{2})",            # 202401
        ]

        selected_match: str | None = None
        selected_start = -1
        selected_end = -1
        for pattern in patterns:
            for match in re.finditer(pattern, filename):
                try:
                    year = int(match.group(1))
                    month = int(match.group(2))
                except ValueError:
                    continue
                if 2000 <= year <= 2099 and 1 <= month <= 12:
                    match_value = f"{year}-{month:02d}"
                    match_start = match.start()
                    match_end = match.end()
                    if selected_match is None:
                        selected_match = match_value
                        selected_start = match_start
                        selected_end = match_end
                        continue
                    if prefer_latest_match:
                        if (match_end, match_start) >= (selected_end, selected_start):
                            selected_match = match_value
                            selected_start = match_start
                            selected_end = match_end
                    elif (match_start, match_end) <= (selected_start, selected_end):
                        selected_match = match_value
                        selected_start = match_start
                        selected_end = match_end
        return selected_match

    def _to_numeric_series(self, df: pd.DataFrame, column_name: str | None) -> pd.Series:
        if not column_name or column_name not in df.columns:
            return pd.Series(0.0, index=df.index, dtype="float64")
        return pd.to_numeric(df[column_name], errors="coerce").fillna(0.0)

    def _normalize_header_key(self, value: Any) -> str:
        return str(value or "").strip().lower().replace("\xa0", "").replace(" ", "").replace("_", "")

    def _find_matching_columns(self, df: pd.DataFrame, candidates: tuple[str, ...]) -> list[str]:
        normalized_candidates = {self._normalize_header_key(candidate) for candidate in candidates}
        matches: list[str] = []
        for column in df.columns:
            column_name = str(column)
            if column_name in candidates or self._normalize_header_key(column_name) in normalized_candidates:
                matches.append(column_name)
        return matches

    def _standardize_result_headers(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        for canonical, aliases in self._HEADER_ALIASES.items():
            candidates = (canonical, *aliases)
            matches = self._find_matching_columns(out, candidates)
            if not matches:
                continue

            if canonical not in out.columns:
                source = matches[0]
                if source != canonical:
                    out = out.rename(columns={source: canonical})
                    matches = [canonical if item == source else item for item in matches]

            if canonical in out.columns:
                for variant in [item for item in matches if item != canonical and item in out.columns]:
                    canonical_series = out[canonical]
                    variant_series = out[variant]
                    if canonical in self._NUMERIC_CANONICAL_COLUMNS:
                        canonical_num = pd.to_numeric(canonical_series, errors="coerce")
                        variant_num = pd.to_numeric(variant_series, errors="coerce")
                        use_variant_mask = (
                            (canonical_num.isna() | (canonical_num.abs() < 1e-9))
                            & variant_num.notna()
                            & (variant_num.abs() >= 1e-9)
                        )
                        out.loc[use_variant_mask, canonical] = variant_series.loc[use_variant_mask]
                    else:
                        missing_mask = canonical_series.isna()
                        if canonical_series.dtype == object:
                            missing_mask = missing_mask | (canonical_series.astype(str).str.strip() == "")
                        out.loc[missing_mask, canonical] = variant_series.loc[missing_mask]
                    out = out.drop(columns=[variant])

        return out

    def _resolve_first_existing_column(self, df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
        for candidate in candidates:
            if candidate in df.columns:
                return candidate
        normalized_candidates = {self._normalize_header_key(candidate) for candidate in candidates}
        for column_name in df.columns:
            if self._normalize_header_key(column_name) in normalized_candidates:
                return str(column_name)
        return None

    def _round2(self, value: float) -> float:
        try:
            return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        except Exception:
            return round(float(value), 2)

    def _normalize_text_cell(self, value: Any) -> str:
        if value is None:
            return "—"
        try:
            if pd.isna(value):
                return "—"
        except Exception:
            pass
        text = str(value).strip()
        if text.lower() in self._TEXT_EMPTY_VALUES:
            return "—"
        return text or "—"

    def _aggregate_text_values(self, series: pd.Series) -> str:
        values = []
        for value in series.tolist():
            normalized = self._normalize_text_cell(value)
            if normalized == "—":
                continue
            values.append(normalized)
        unique_values = sorted(set(values))
        if not unique_values:
            return "—"
        if len(unique_values) == 1:
            return unique_values[0]
        return "多类型"

    def _resolve_dst_column(self, df: pd.DataFrame) -> str | None:
        for candidate in self._DST_COLUMN_CANDIDATES:
            if candidate in df.columns:
                return candidate
        for column_name in df.columns:
            normalized = self._normalize_header_key(column_name)
            if normalized == self._normalize_header_key(self._DST_COLUMN_NORMALIZED):
                return str(column_name)
        for column_name in df.columns:
            normalized = self._normalize_header_key(column_name)
            if any(alias in normalized for alias in self._DST_COLUMN_FUZZY_ALIASES):
                return column_name
        return None

    def _build_client_account_result_column_names(self, month_column: str) -> tuple[str, str, str, str]:
        text = str(month_column or "").strip()
        if "消耗" in text:
            prefix = text.replace("消耗", "", 1)
        else:
            prefix = text
        return (
            f"{prefix}服务费",
            f"{prefix}固定服务费",
            f"{prefix}换汇汇率",
            f"{prefix}换汇后消耗USD",
        )

    def _expand_client_account_result_sheet(self, df_sheet: pd.DataFrame, sheet_name: str) -> pd.DataFrame:
        if df_sheet.empty or not self._is_client_account_sheet_name(sheet_name):
            return pd.DataFrame()

        currency_series = df_sheet.apply(self._infer_client_account_currency, axis=1)
        frames: list[pd.DataFrame] = []

        for column_name in df_sheet.columns:
            month_key = self._extract_client_account_month(column_name)
            if not month_key:
                continue

            service_col, fixed_col, fx_col, usd_col = self._build_client_account_result_column_names(str(column_name))
            if not any(col in df_sheet.columns for col in (service_col, fixed_col, fx_col, usd_col)):
                continue

            consumption_series = self._to_numeric_series(df_sheet, str(column_name))
            service_series = self._to_numeric_series(df_sheet, service_col)
            fixed_series = self._to_numeric_series(df_sheet, fixed_col)
            fx_series = (
                pd.to_numeric(df_sheet[fx_col], errors="coerce")
                if fx_col in df_sheet.columns
                else pd.Series(float("nan"), index=df_sheet.index, dtype="float64")
            )
            usd_series = (
                pd.to_numeric(df_sheet[usd_col], errors="coerce")
                if usd_col in df_sheet.columns
                else pd.Series(float("nan"), index=df_sheet.index, dtype="float64")
            )

            managed_usd_series = usd_series.fillna(0.0)
            use_original_mask = managed_usd_series.abs() < 1e-9
            managed_usd_series.loc[use_original_mask] = consumption_series.loc[use_original_mask]

            needs_conversion_mask = (
                currency_series.isin({"RMB", "JPY", "EUR"})
                & use_original_mask
                & fx_series.notna()
                & (fx_series.abs() >= 1e-9)
            )
            managed_usd_series.loc[needs_conversion_mask] = (
                consumption_series.loc[needs_conversion_mask] * fx_series.loc[needs_conversion_mask]
            )

            active_mask = (
                (consumption_series.abs() >= 1e-9)
                | (service_series.abs() >= 1e-9)
                | (fixed_series.abs() >= 1e-9)
                | (managed_usd_series.abs() >= 1e-9)
            )
            if not bool(active_mask.any()):
                continue

            frame = pd.DataFrame(
                {
                    "母公司": df_sheet.get("母公司"),
                    "媒介": df_sheet.get("媒介"),
                    "币种": currency_series,
                    "服务类型": "代投",
                    "代投消耗": managed_usd_series,
                    "流水消耗": 0.0,
                    "汇总纯花费": managed_usd_series,
                    "服务费": service_series,
                    "固定服务费": fixed_series,
                    "换汇汇率": fx_series.where(fx_series.abs() >= 1e-9, 1.0),
                    "月份归属": month_key,
                    "来源Sheet": sheet_name,
                }
            )
            if "预付/后付" in df_sheet.columns:
                frame["预付/后付"] = df_sheet["预付/后付"]
            frames.append(frame.loc[active_mask].copy())

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True, sort=False)

    def _load_visible_result_workbook_dataframe(
        self,
        result_source: str | Path,
        sheet_names: list[str],
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        for sheet_name in sheet_names:
            if sheet_name == self._RESULT_DATA_SHEET_NAME:
                continue

            df_sheet = pd.read_excel(result_source, sheet_name=sheet_name)
            if df_sheet.empty:
                continue

            if self._is_client_account_sheet_name(sheet_name):
                expanded_df = self._expand_client_account_result_sheet(df_sheet, sheet_name)
                if not expanded_df.empty:
                    frames.append(expanded_df)
                continue

            columns = {str(col).strip() for col in df_sheet.columns.tolist()}
            if not {"母公司", "媒介"}.issubset(columns):
                continue
            frames.append(df_sheet.copy())

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True, sort=False)

    def _load_result_dataframe_with_context(
        self,
        result_source: str | Path | pd.DataFrame,
        *,
        operation: str | None = None,
    ) -> tuple[pd.DataFrame, str]:
        if isinstance(result_source, pd.DataFrame):
            return result_source.copy(), "dataframe"

        sheet_name: str | int = 0
        sheet_names: list[str] = []
        use_visible_workbook_fallback = False
        load_mode = "single_sheet"
        workbook = self._open_excel_workbook(str(result_source), context="计算结果文件")
        try:
            sheet_names = list(workbook.sheet_names)
            if operation in self._ESTIMATE_RESULT_OPERATIONS:
                if self._ESTIMATE_OUTPUT_SHEET_NAME in workbook.sheet_names:
                    sheet_name = self._ESTIMATE_OUTPUT_SHEET_NAME
            elif self._RESULT_DATA_SHEET_NAME in workbook.sheet_names:
                sheet_name = self._RESULT_DATA_SHEET_NAME
                load_mode = "calc_data_sheet"
            elif len(workbook.sheet_names) > 1:
                use_visible_workbook_fallback = True
                load_mode = "visible_multi_sheet"
        finally:
            workbook.close()

        if use_visible_workbook_fallback:
            return self._load_visible_result_workbook_dataframe(result_source, sheet_names), load_mode
        return pd.read_excel(result_source, sheet_name=sheet_name), load_mode

    def _load_result_dataframe(
        self,
        result_source: str | Path | pd.DataFrame,
        *,
        operation: str | None = None,
    ) -> pd.DataFrame:
        df, _ = self._load_result_dataframe_with_context(result_source, operation=operation)
        return df

    def _prepare_result_month_batches(
        self,
        filename: str,
        result_source: str | Path | pd.DataFrame,
        *,
        filename_month: str | None = None,
    ) -> list[tuple[str, pd.DataFrame]]:
        result_df, load_mode = self._load_result_dataframe_with_context(result_source)
        month_str = (
            filename_month
            if filename_month and self._is_valid_month_string(filename_month)
            else self._parse_month_from_filename(filename)
        )

        normalized_df = self._standardize_result_headers(result_df.copy())
        normalized_df["_client_name"] = (
            normalized_df["母公司"].apply(self._normalize_text_cell)
            if "母公司" in normalized_df.columns
            else "—"
        )
        normalized_df = normalized_df[normalized_df["_client_name"] != "—"].copy()

        if normalized_df.empty:
            return []

        normalized_df["_bill_type"] = (
            normalized_df["预付/后付"].apply(self._normalize_text_cell)
            if "预付/后付" in normalized_df.columns
            else "—"
        )
        normalized_df["_service_type"] = (
            normalized_df["服务类型"].apply(self._normalize_text_cell)
            if "服务类型" in normalized_df.columns
            else "—"
        )
        normalized_df["_flow_consumption"] = self._to_numeric_series(normalized_df, "流水消耗")
        normalized_df["_managed_consumption"] = self._to_numeric_series(normalized_df, "代投消耗")
        net_column = self._resolve_first_existing_column(normalized_df, self._NET_CONSUMPTION_COLUMN_CANDIDATES)
        net_consumption = self._to_numeric_series(normalized_df, net_column)
        combined_consumption = normalized_df["_flow_consumption"] + normalized_df["_managed_consumption"]
        normalized_df["_service_fee"] = self._to_numeric_series(normalized_df, "服务费")
        normalized_df["_fixed_service_fee"] = self._to_numeric_series(normalized_df, "固定服务费")
        coupon_column = self._resolve_first_existing_column(normalized_df, self._COUPON_COLUMN_CANDIDATES)
        normalized_df["_coupon"] = self._to_numeric_series(normalized_df, coupon_column)

        dst_column = self._resolve_dst_column(normalized_df)
        normalized_df["_dst"] = self._to_numeric_series(normalized_df, dst_column)
        fx_rate = self._to_numeric_series(normalized_df, "换汇汇率")
        normalized_df["_fx_rate"] = fx_rate.where(fx_rate.abs() > 1e-9, 1.0)

        converted_has_value = combined_consumption.abs() > 1e-9
        net_spend_for_total = (net_consumption * normalized_df["_fx_rate"]).where(~converted_has_value, combined_consumption)
        normalized_df["_net_consumption"] = net_spend_for_total
        normalized_df["_total"] = (
            net_spend_for_total
            + normalized_df["_service_fee"]
            + normalized_df["_fixed_service_fee"]
            + normalized_df["_coupon"]
            + normalized_df["_dst"]
        ).apply(self._round2)

        normalized_df["_temp_consumption"] = combined_consumption
        normalized_df["_temp_fee"] = (
            normalized_df["_service_fee"] + normalized_df["_fixed_service_fee"]
        )

        months_to_process: list[tuple[str, pd.DataFrame]] = []
        has_month_col = False
        prefer_filename_month = (
            load_mode in {"calc_data_sheet", "visible_multi_sheet"}
            and bool(month_str)
            and self._is_valid_month_string(month_str)
        )

        if "月份归属" in normalized_df.columns and not normalized_df["月份归属"].isnull().all():
            has_month_col = True
            try:
                normalized_df["_month"] = normalized_df["月份归属"].apply(self._normalize_month_value)
                if prefer_filename_month:
                    monthly_df = normalized_df[
                        normalized_df["_month"].isna() | (normalized_df["_month"] == month_str)
                    ].copy()
                    dropped_other_month_count = int(len(normalized_df) - len(monthly_df))
                    if monthly_df.empty:
                        monthly_df = normalized_df.copy()
                        dropped_other_month_count = 0
                    monthly_df["_month"] = month_str
                    if dropped_other_month_count:
                        logger.info(
                            "结果文件 %s 按文件月份 %s 回填，已忽略 %s 行其他月份数据",
                            filename,
                            month_str,
                            dropped_other_month_count,
                        )
                    months_to_process.append((month_str, monthly_df))
                    return months_to_process

                valid_date_df = normalized_df.dropna(subset=["_month"])

                if not valid_date_df.empty:
                    invalid_count = int((normalized_df["月份归属"].notna() & normalized_df["_month"].isna()).sum())
                    if invalid_count:
                        logger.warning("月份归属列有 %s 行无法识别月份，已忽略", invalid_count)
                    for month_key, group in valid_date_df.groupby("_month"):
                        if self._is_valid_month_string(str(month_key)):
                            months_to_process.append((str(month_key), group.copy()))
                else:
                    has_month_col = False
            except Exception as exc:
                logger.warning("按月份归属分组失败，回退到单月模式: %s", exc)
                has_month_col = False

        if not has_month_col:
            if not month_str or not self._is_valid_month_string(month_str):
                raise HTTPException(status_code=400, detail=f"无法从文件名 '{filename}' 或数据列 '月份归属' 识别有效月份。")
            months_to_process.append((month_str, normalized_df.copy()))

        return months_to_process

    def _update_stats_from_result(self, filename: str, output_path: str):
        """Parse result Excel and update monthly client and billing stats."""
        try:
            months_to_process = self._prepare_result_month_batches(filename, output_path)
            for month_key, current_df in months_to_process:
                self._upsert_monthly_stats_with_retry(month_key, current_df)

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("统计保存失败: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"统计保存失败: {exc}")

    def _upsert_monthly_stats_with_retry(
        self,
        month: str,
        df: pd.DataFrame,
        retries: int = 3,
        db: Session | None = None,
    ):
        last_exc = None
        for attempt in range(1, retries + 1):
            try:
                self._upsert_monthly_stats(month, df, db=db)
                return
            except OperationalError as exc:
                last_exc = exc
                msg = str(exc).lower()
                retryable = any(token in msg for token in ("database is locked", "disk i/o error", "busy"))
                if not retryable or attempt >= retries:
                    break
                wait_seconds = 0.4 * attempt
                logger.warning(
                    "月度统计写入失败，准备重试 (%s/%s), month=%s, error=%s",
                    attempt,
                    retries,
                    month,
                    exc,
                )
                time.sleep(wait_seconds)

        if last_exc is not None:
            raise last_exc

    def _upsert_monthly_stats(self, month: str, df: pd.DataFrame, db: Session | None = None):
        stats_list: list[dict[str, float | str]] = []
        detail_stats_list: list[dict[str, float | str]] = []
        if "_client_name" in df.columns:
            client_stats = df.groupby("_client_name")[["_temp_consumption", "_temp_fee"]].sum().reset_index()
            client_stats = client_stats[(client_stats["_temp_consumption"] != 0) | (client_stats["_temp_fee"] != 0)]

            stats_list = [
                {
                    "name": str(row["_client_name"]).strip(),
                    "consumption": float(row["_temp_consumption"] or 0.0),
                    "fee": float(row["_temp_fee"] or 0.0),
                }
                for _, row in client_stats.iterrows()
                if pd.notna(row["_client_name"]) and str(row["_client_name"]).strip()
            ]

            for client_name, group in df.groupby("_client_name"):
                client_label = str(client_name).strip()
                if not client_label:
                    continue
                detail_payload = {
                    "name": client_label,
                    "bill_type": self._aggregate_text_values(group["_bill_type"]),
                    "service_type": self._aggregate_text_values(group["_service_type"]),
                    "flow_consumption": float(group["_flow_consumption"].sum() or 0.0),
                    "managed_consumption": float(group["_managed_consumption"].sum() or 0.0),
                    "net_consumption": float(group["_net_consumption"].sum() or 0.0),
                    "service_fee": float(group["_service_fee"].sum() or 0.0),
                    "fixed_service_fee": float(group["_fixed_service_fee"].sum() or 0.0),
                    "coupon": float(group["_coupon"].sum() or 0.0),
                    "dst": float(group["_dst"].sum() or 0.0),
                    "total": float(group["_total"].sum() or 0.0),
                }
                has_activity = any(
                    abs(float(detail_payload[key] or 0.0)) >= 1e-9
                    for key in (
                        "flow_consumption",
                        "managed_consumption",
                        "net_consumption",
                        "service_fee",
                        "fixed_service_fee",
                        "coupon",
                        "dst",
                        "total",
                    )
                )
                if has_activity:
                    detail_stats_list.append(detail_payload)

        replace_client_stats_batch(month, stats_list, db=db)
        replace_client_detail_stats_batch(month, detail_stats_list, db=db)

        total_consumption = float(df["_temp_consumption"].sum() or 0.0)
        total_fee = float(df["_temp_fee"].sum() or 0.0)
        has_month_activity = abs(total_consumption) >= 1e-9 or abs(total_fee) >= 1e-9

        if has_month_activity:
            upsert_billing_history(month, total_consumption, total_fee, db=db)
        else:
            should_close = False
            billing_db = db
            if billing_db is None:
                billing_db = SessionLocal()
                should_close = True
            try:
                billing_db.query(BillingHistory).filter(BillingHistory.month == month).delete(synchronize_session=False)
                billing_db.commit()
            finally:
                if should_close:
                    billing_db.close()

        logger.info("Month %s: Total Consumption %s, Total Fee %s", month, total_consumption, total_fee)

    def _get_results_file_signature(
        self,
        result_entries: list[dict[str, Any]] | None = None,
    ) -> tuple[tuple[str, int, int, str], ...]:
        signature_parts: list[tuple[str, int, int, str]] = []
        entries = result_entries if result_entries is not None else self._get_dashboard_result_entries()
        for entry in entries:
            result_path = Path(entry["path"])
            try:
                stat = result_path.stat()
            except FileNotFoundError:
                continue
            signature_parts.append(
                (
                    str(entry.get("filename") or result_path.name),
                    stat.st_mtime_ns,
                    stat.st_size,
                    str(entry.get("source_file") or ""),
                )
            )
        return tuple(signature_parts)

    def _get_dashboard_backfill_signature_path(self) -> Path:
        return self._get_upload_dir() / self._DASHBOARD_BACKFILL_SIGNATURE_FILE

    def _read_dashboard_backfill_signature(self) -> tuple[tuple[str, int, int, str], ...] | None:
        signature_path = self._get_dashboard_backfill_signature_path()
        try:
            payload = json.loads(signature_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None

        raw_signature = payload.get("signature") if isinstance(payload, dict) else None
        if not isinstance(raw_signature, list):
            return None

        signature_parts: list[tuple[str, int, int, str]] = []
        for item in raw_signature:
            if not isinstance(item, (list, tuple)) or len(item) != 4:
                return None
            try:
                signature_parts.append((str(item[0]), int(item[1]), int(item[2]), str(item[3])))
            except (TypeError, ValueError):
                return None
        return tuple(signature_parts)

    def _write_dashboard_backfill_signature(self, signature: tuple[tuple[str, int, int, str], ...]) -> None:
        signature_path = self._get_dashboard_backfill_signature_path()
        tmp_path = signature_path.with_suffix(f"{signature_path.suffix}.tmp")
        payload = {
            "signature": [list(item) for item in signature],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        try:
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_path.replace(signature_path)
        except OSError as exc:
            logger.warning("Dashboard backfill signature cache write skipped: %s", exc)

    def _dashboard_snapshot_tables_have_data(self, db: Session | None) -> bool:
        should_close = False
        snapshot_db = db
        if snapshot_db is None:
            snapshot_db = SessionLocal()
            should_close = True
        try:
            return bool(
                snapshot_db.query(BillingHistory.month).first()
                and snapshot_db.query(ClientMonthlyStats.id).first()
                and snapshot_db.query(ClientMonthlyDetailStats.id).first()
            )
        finally:
            if should_close:
                snapshot_db.close()

    def _reset_dashboard_snapshot_tables(self, db: Session) -> None:
        db.query(ClientMonthlyDetailStats).delete(synchronize_session=False)
        db.query(ClientMonthlyStats).delete(synchronize_session=False)
        db.query(BillingHistory).delete(synchronize_session=False)
        db.commit()

    def backfill_detail_stats_from_results(self, db: Session | None = None) -> None:
        if os.getenv("TESTING") == "True":
            return

        result_entries = self._get_dashboard_result_entries()
        signature = self._get_results_file_signature(result_entries)
        if not signature:
            return

        if signature == self._detail_backfill_signature:
            return

        has_existing_snapshot = self._dashboard_snapshot_tables_have_data(db)
        if has_existing_snapshot:
            cached_signature = self._read_dashboard_backfill_signature()
            if signature == cached_signature:
                self._detail_backfill_signature = signature
                return

        with self._detail_backfill_lock:
            if signature == self._detail_backfill_signature:
                return
            has_existing_snapshot = self._dashboard_snapshot_tables_have_data(db)
            if has_existing_snapshot:
                cached_signature = self._read_dashboard_backfill_signature()
                if signature == cached_signature:
                    self._detail_backfill_signature = signature
                    return

            prepared_batches: list[tuple[str, pd.DataFrame]] = []
            failures: list[tuple[str, Exception]] = []
            for entry in result_entries:
                result_path = Path(entry["path"])
                filename = str(entry.get("filename") or result_path.name)
                source_file = str(entry.get("source_file") or "").strip()
                month_hint = (
                    self._parse_month_from_filename(source_file)
                    if source_file
                    else self._parse_month_from_filename(filename, prefer_latest_match=True)
                )
                try:
                    months_to_process = self._prepare_result_month_batches(
                        source_file or filename,
                        result_path,
                        filename_month=month_hint,
                    )
                    prepared_batches.extend(months_to_process)
                except Exception as exc:
                    failures.append((filename, exc))

            if failures:
                if has_existing_snapshot:
                    for month_key, current_df in prepared_batches:
                        self._upsert_monthly_stats(month_key, current_df, db=db)
                    self._detail_backfill_signature = signature
                    self._write_dashboard_backfill_signature(signature)
                for filename, exc in failures:
                    logger.warning("鍘嗗彶璐﹀崟鏄庣粏鍥炲～澶辫触: %s (%s)", filename, exc)
                logger.warning("鍘嗗彶璐﹀崟鏄庣粏鍥炲～宸蹭繚鐣欐棫蹇収锛屾湰娆℃湭瑕嗙洊鏁版嵁")
                return

            if not prepared_batches:
                if has_existing_snapshot:
                    self._detail_backfill_signature = signature
                    self._write_dashboard_backfill_signature(signature)
                return

            self._reset_dashboard_snapshot_tables(db)
            for month_key, current_df in prepared_batches:
                self._upsert_monthly_stats(month_key, current_df, db=db)
            self._detail_backfill_signature = signature
            self._write_dashboard_backfill_signature(signature)
            return

            self._reset_dashboard_snapshot_tables(db)

            for filename, _, _ in signature:
                result_path = self._get_upload_dir() / filename
                if not result_path.exists():
                    continue
                try:
                    months_to_process = self._prepare_result_month_batches(filename, result_path)
                    for month_key, current_df in months_to_process:
                        self._upsert_monthly_stats(month_key, current_df, db=db)
                except Exception as exc:
                    logger.warning("历史账单明细回填失败: %s (%s)", filename, exc)

            self._detail_backfill_signature = signature

    def get_results_data(self, result_ref: str, owner_username: str):
        record = self._resolve_result_record_for_user(result_ref, owner_username)
        file_path = self._resolve_result_file(record["filename"])
        operation = str(record.get("operation") or "")
        df = self._load_result_dataframe(file_path, operation=operation)

        for col in df.columns:
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                df[col] = df[col].dt.strftime("%Y-%m-%d")
            elif ("月" in str(col) or "日期" in str(col) or "date" in str(col).lower()):
                numeric_vals = pd.to_numeric(df[col], errors="coerce")
                if numeric_vals.notna().any() and (numeric_vals.dropna() > 40000).all() and (numeric_vals.dropna() < 55000).all():

                    def excel_serial_to_date(serial):
                        try:
                            serial_float = float(serial)
                            dt = datetime(1899, 12, 30) + timedelta(days=serial_float)
                            return dt.strftime("%Y-%m")
                        except (ValueError, TypeError):
                            return serial

                    df[col] = df[col].apply(excel_serial_to_date)

        result_df = df.fillna("")
        return {
            "columns": result_df.columns.tolist(),
            "data": result_df.to_dict("records"),
            "total": len(result_df),
        }

    def get_download_path(self, result_ref: str, owner_username: str) -> Path:
        try:
            record = self._resolve_result_record_for_user(result_ref, owner_username)
            file_path = self._resolve_result_file(record["filename"])
            self._audit(
                action="download_result",
                actor=owner_username,
                status="success",
                input_file=record.get("source_file"),
                output_file=record.get("filename"),
                result_ref=str(record.get("id") or result_ref),
            )
            return file_path
        except HTTPException as exc:
            self._audit(
                action="download_result",
                actor=owner_username,
                status="failed",
                result_ref=result_ref,
                error_message=str(exc.detail),
            )
            raise

    async def process_contract_upload(self, file: UploadFile, owner_username: str = "system"):
        upload_dir = self._get_upload_dir()
        safe_filename = secure_filename(file.filename)
        self._validate_excel_extension(safe_filename, context="合同上传文件")
        file_path = upload_dir / safe_filename

        try:
            with open(file_path, "wb") as f:
                shutil.copyfileobj(file.file, f)
            self._validate_contract_workbook(str(file_path))

            from api.migrate import migrate_from_excel

            count = migrate_from_excel(str(file_path))
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="success",
                input_file=safe_filename,
                metadata={"imported_count": count},
            )
            return {
                "status": "ok",
                "message": f"成功导入 {count} 条客户记录",
            }
        except HTTPException as exc:
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc.detail),
            )
            raise
        except ValueError as exc:
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc),
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            self._audit(
                action="upload_contract",
                actor=owner_username,
                status="failed",
                input_file=safe_filename,
                error_message=str(exc),
            )
            logger.error("Contract upload failed: %s", exc, exc_info=True)
            raise HTTPException(status_code=500, detail=str(exc))
