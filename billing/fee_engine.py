# -*- coding: utf-8 -*-
"""Billing fee calculation engine."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import pandas as pd

from .clause_parser import parse_fee_clause
from .client_overrides import apply_post_overrides
from .contract_loader import (
    extract_date_from_filename,
    load_contract_terms,
    load_contract_terms_from_db,
    load_contract_terms_from_feishu,
)

logger = logging.getLogger(__name__)

_COL_CLIENT = "\u6bcd\u516c\u53f8"
_COL_MEDIA = "\u5a92\u4ecb"
_COL_SERVICE_TYPE = "\u670d\u52a1\u7c7b\u578b"
_COL_MANAGED_CONSUMPTION = "\u4ee3\u6295\u6d88\u8017"
_COL_FLOW_CONSUMPTION = "\u6d41\u6c34\u6d88\u8017"
_COL_NET_SPEND = "\u6c47\u603b\u7eaf\u82b1\u8d39"
_COL_NET_SPEND_ALT = "\u6c47\u603b\u7eaf\u6d88\u8017"
_COL_BILL_TOTAL = "\u8d26\u5355\u6c47\u603b"
_COL_MANAGED_SPLIT = "\u4ee3\u6295/\u54a8\u8be2\u62c6\u5206"
_COL_FLOW_SPLIT = "\u6d41\u6c34\u62c6\u5206"
_COL_FX_RATE = "\u6362\u6c47\u6c47\u7387"
_COL_SERVICE_FEE = "\u670d\u52a1\u8d39"
_COL_FIXED_SERVICE_FEE = "\u56fa\u5b9a\u670d\u52a1\u8d39"
_COL_COUPON = "Coupon"
_COL_TOTAL = "\u6c47\u603b"
_COL_DST_CANON = "\u76d1\u7ba1\u8fd0\u8425\u8d39\u7528/\u6570\u5b57\u670d\u52a1\u7a0e(DST)"
_COL_SOURCE_SHEET = "\u6765\u6e90Sheet"
_HIDDEN_RESULT_SHEET_NAME = "_CALC_DATA"
_CLIENT_ACCOUNT_SHEET_MARKERS = (
    "\u5ba2\u6237\u7aef\u53e3\u8d26\u6237\u4ee3\u6295",
    "\u5ba2\u6237\u7aef\u53e3\u4ee3\u6295",
)
_INTERNAL_SOURCE_ROW_COLUMN = "_\u6765\u6e90\u884c\u53f7"
_INTERNAL_TARGET_MONTH_COLUMN = "_\u76ee\u6807\u6708\u6d88\u8017\u5217"
_VISIBLE_FX_AUDIT_COLUMNS = (
    "\u539f\u59cb\u4ee3\u6295\u6d88\u8017",
    "\u539f\u59cb\u6d41\u6c34\u6d88\u8017",
    "\u6362\u6c47\u6c47\u7387",
    "\u6c47\u7387\u6765\u6e90",
    "\u6c47\u7387\u65e5\u671f",
    "\u6362\u6c47\u540e\u4ee3\u6295\u6d88\u8017USD",
    "\u6362\u6c47\u540e\u6d41\u6c34\u6d88\u8017USD",
)

_DST_COLUMN_CANDIDATES = (
    "\u76d1\u7ba1\u8fd0\u8425\u8d39\u7528/\u6570\u5b57\u670d\u52a1\u7a0e(DST)\xa0",
    "\u76d1\u7ba1\u8fd0\u8425\u8d39\u7528/\u6570\u5b57\u670d\u52a1\u7a0e (DST)\xa0",
    "\u76d1\u7ba1\u8fd0\u8425\u8d39\u7528/\u6570\u5b57\u670d\u52a1\u7a0e(DST)",
    "\u76d1\u7ba1\u8fd0\u8425\u8d39\u7528/\u6570\u5b57\u670d\u52a1\u7a0e (DST)",
)
_DST_COLUMN_NORMALIZED = _COL_DST_CANON
_DST_COLUMN_FUZZY_ALIASES = (
    "\u76d1\u7ba1\u8d39",
    "\u76d1\u7ba1\u8fd0\u8425\u8d39",
    "\u6570\u5b57\u670d\u52a1\u7a0e",
    "dst",
)

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    _COL_CLIENT: (f"{_COL_CLIENT} ",),
    _COL_MEDIA: (f"{_COL_MEDIA} ",),
    _COL_SERVICE_TYPE: (f"{_COL_SERVICE_TYPE} ",),
    _COL_MANAGED_CONSUMPTION: (f"{_COL_MANAGED_CONSUMPTION} ",),
    _COL_FLOW_CONSUMPTION: (f"{_COL_FLOW_CONSUMPTION} ",),
    _COL_NET_SPEND: (
        _COL_NET_SPEND_ALT,
        f"{_COL_NET_SPEND} ",
        f"{_COL_NET_SPEND_ALT} ",
        f"{_COL_NET_SPEND}(USD)",
        f"{_COL_NET_SPEND_ALT}(USD)",
    ),
    _COL_FX_RATE: (f"{_COL_FX_RATE} ",),
    _COL_SERVICE_FEE: (f"{_COL_SERVICE_FEE} ",),
    _COL_FIXED_SERVICE_FEE: (f"{_COL_FIXED_SERVICE_FEE} ",),
    _COL_COUPON: ("COUPON", "coupon", f"{_COL_COUPON} "),
    _COL_TOTAL: ("Summary", "\u5408\u8ba1", "\u603b\u8ba1", f"{_COL_TOTAL} "),
    _COL_DST_CANON: (*_DST_COLUMN_CANDIDATES, *_DST_COLUMN_FUZZY_ALIASES),
}

_NUMERIC_CANONICAL_COLUMNS = {
    _COL_MANAGED_CONSUMPTION,
    _COL_FLOW_CONSUMPTION,
    _COL_NET_SPEND,
    _COL_FX_RATE,
    _COL_SERVICE_FEE,
    _COL_FIXED_SERVICE_FEE,
    _COL_COUPON,
    _COL_TOTAL,
    _COL_DST_CANON,
}


def _round2(value: float) -> float:
    """Standard half-up rounding to 2 decimal places (财务四舍五入)."""
    try:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:
        return round(float(value), 2)


def _is_managed_service_type(service_type: str) -> bool:
    """Return True when current row should be treated as managed-delivery fee scope."""
    return "代投" in str(service_type or "")


def _normalize_service_type(service_type: str) -> str:
    """
    Normalize service type variants to canonical labels used by fee branches.

    Canonical values:
    - 代投
    - 流水
    - 代投+流水
    """
    text = str(service_type or "").strip()
    if not text:
        return ""

    compact = (
        text.replace(" ", "")
        .replace("\u3000", "")
        .replace("＋", "+")
        .replace("/", "+")
        .replace("、", "+")
        .replace("|", "+")
    )
    if "代投" in compact and "流水" in compact:
        return "代投+流水"
    if "代投" in compact:
        return "代投"
    if "流水" in compact:
        return "流水"
    return text


def _to_float(value) -> float:
    """Convert mixed spreadsheet values to float safely."""
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except Exception:
        pass

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text or text in {"-", "/", "—"}:
        return 0.0

    cleaned = (
        text.replace(",", "")
        .replace("，", "")
        .replace("$", "")
        .replace("￥", "")
        .replace("¥", "")
        .replace("\xa0", "")
        .strip()
    )
    parsed = pd.to_numeric(cleaned, errors="coerce")
    return float(parsed) if pd.notna(parsed) else 0.0


def _normalize_header_key(value: object) -> str:
    return str(value or "").strip().lower().replace("\xa0", "").replace(" ", "").replace("_", "")


def _find_matching_columns(df: pd.DataFrame, candidates: tuple[str, ...]) -> list[str]:
    normalized_candidates = {_normalize_header_key(candidate) for candidate in candidates}
    matches: list[str] = []
    for column in df.columns:
        if str(column) in candidates or _normalize_header_key(column) in normalized_candidates:
            matches.append(str(column))
    return matches


def _standardize_headers(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for canonical, aliases in _HEADER_ALIASES.items():
        candidates = (canonical, *aliases)
        matches = _find_matching_columns(out, candidates)
        if not matches:
            continue

        # Prefer canonical header in output; otherwise rename the first matched variant.
        if canonical not in out.columns:
            source = matches[0]
            if source != canonical:
                out = out.rename(columns={source: canonical})
                matches = [canonical if m == source else m for m in matches]

        # If multiple variants coexist, merge sparse values into canonical then drop variants.
        if canonical in out.columns:
            for variant in [m for m in matches if m != canonical and m in out.columns]:
                canonical_series = out[canonical]
                variant_series = out[variant]
                if canonical in _NUMERIC_CANONICAL_COLUMNS:
                    # Keep numeric canonical columns in float space to avoid
                    # pandas dtype upcast errors when merging decimal variants.
                    canonical_num = pd.to_numeric(canonical_series, errors="coerce").astype(float)
                    variant_num = pd.to_numeric(variant_series, errors="coerce")
                    use_variant_mask = (
                        (canonical_num.isna() | (canonical_num.abs() < 1e-9))
                        & variant_num.notna()
                        & (variant_num.abs() >= 1e-9)
                    )
                    out[canonical] = canonical_num
                    out.loc[use_variant_mask, canonical] = variant_num.loc[use_variant_mask]
                else:
                    missing_mask = canonical_series.isna()
                    if canonical_series.dtype == object:
                        missing_mask = missing_mask | (canonical_series.astype(str).str.strip() == "")
                    out.loc[missing_mask, canonical] = variant_series.loc[missing_mask]
                out = out.drop(columns=[variant])


    return out


def _numeric_series(df: pd.DataFrame, column_name: str) -> pd.Series:
    if column_name not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype="float64")
    return pd.to_numeric(df[column_name], errors="coerce")


def _missing_numeric_mask(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.isna() | (numeric.abs() < 1e-9)


def _populate_consumption_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Some foreign-currency sheets store spend in bill-summary columns instead of
    the canonical managed/flow columns. Hydrate the canonical columns so the
    fee engine and dashboard use the same converted spend basis.
    """
    out = df.copy()
    if out.empty:
        return out

    if _COL_MANAGED_CONSUMPTION not in out.columns:
        out[_COL_MANAGED_CONSUMPTION] = 0.0
    if _COL_FLOW_CONSUMPTION not in out.columns:
        out[_COL_FLOW_CONSUMPTION] = 0.0
    if _COL_NET_SPEND not in out.columns:
        out[_COL_NET_SPEND] = 0.0

    service_type_series = (
        out[_COL_SERVICE_TYPE].apply(_normalize_service_type)
        if _COL_SERVICE_TYPE in out.columns
        else pd.Series("", index=out.index, dtype="object")
    )

    managed_split = _numeric_series(out, _COL_MANAGED_SPLIT)
    flow_split = _numeric_series(out, _COL_FLOW_SPLIT)
    bill_total = _numeric_series(out, _COL_BILL_TOTAL)

    managed_values = _numeric_series(out, _COL_MANAGED_CONSUMPTION)
    flow_values = _numeric_series(out, _COL_FLOW_CONSUMPTION)
    total_values = _numeric_series(out, _COL_NET_SPEND)

    use_managed_split = _missing_numeric_mask(managed_values) & managed_split.notna() & (managed_split.abs() >= 1e-9)
    out.loc[use_managed_split, _COL_MANAGED_CONSUMPTION] = managed_split.loc[use_managed_split]

    use_flow_split = _missing_numeric_mask(flow_values) & flow_split.notna() & (flow_split.abs() >= 1e-9)
    out.loc[use_flow_split, _COL_FLOW_CONSUMPTION] = flow_split.loc[use_flow_split]

    managed_values = _numeric_series(out, _COL_MANAGED_CONSUMPTION)
    flow_values = _numeric_series(out, _COL_FLOW_CONSUMPTION)

    use_bill_total_for_managed = (
        _missing_numeric_mask(managed_values)
        & (service_type_series == "\u4ee3\u6295")
        & bill_total.notna()
        & (bill_total.abs() >= 1e-9)
    )
    out.loc[use_bill_total_for_managed, _COL_MANAGED_CONSUMPTION] = bill_total.loc[use_bill_total_for_managed]

    use_bill_total_for_flow = (
        _missing_numeric_mask(flow_values)
        & (service_type_series == "\u6d41\u6c34")
        & bill_total.notna()
        & (bill_total.abs() >= 1e-9)
    )
    out.loc[use_bill_total_for_flow, _COL_FLOW_CONSUMPTION] = bill_total.loc[use_bill_total_for_flow]

    split_total = (
        pd.to_numeric(out[_COL_MANAGED_CONSUMPTION], errors="coerce").fillna(0.0)
        + pd.to_numeric(out[_COL_FLOW_CONSUMPTION], errors="coerce").fillna(0.0)
    )
    total_values = _numeric_series(out, _COL_NET_SPEND)
    use_split_total_for_total = _missing_numeric_mask(total_values) & (split_total.abs() >= 1e-9)
    out.loc[use_split_total_for_total, _COL_NET_SPEND] = split_total.loc[use_split_total_for_total]

    total_values = _numeric_series(out, _COL_NET_SPEND)
    use_bill_total_for_total = _missing_numeric_mask(total_values) & bill_total.notna() & (bill_total.abs() >= 1e-9)
    out.loc[use_bill_total_for_total, _COL_NET_SPEND] = bill_total.loc[use_bill_total_for_total]

    return out


def _normalize_sheet_currency(sheet_name: str) -> Optional[str]:
    name = str(sheet_name or "").strip().lower().replace(" ", "")
    if any(token in name for token in {"jpy", "日元", "日币"}):
        return "JPY"
    if any(token in name for token in {"eur", "欧元"}):
        return "EUR"
    if any(token in name for token in {"rmb", "cny", "人民币"}):
        return "RMB"
    if any(token in name for token in {"usd", "美元", "美金", "us$"}):
        return "USD"
    if "其他" in name:
        return "OTHER"
    return None


def _normalize_currency_value(value) -> str:
    """Normalize free-text currency labels to canonical currency codes."""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    text = str(value or "").strip().upper().replace(" ", "")
    if text in {"CNY", "RMB", "人民币", "RENMINBI"}:
        return "RMB"
    if text in {"EUR", "欧元"}:
        return "EUR"
    if text in {"JPY", "日元", "日币", "日圆"}:
        return "JPY"
    if text in {"USD", "美元", "US$"}:
        return "USD"
    return text


def _match_currency_hint(value) -> str:
    text = str(value or "").strip().upper().replace(" ", "")
    if not text:
        return ""
    if any(token in text for token in {"CNY", "RMB", "人民币", "RENMINBI"}):
        return "RMB"
    if any(token in text for token in {"EUR", "欧元"}):
        return "EUR"
    if any(token in text for token in {"JPY", "日元", "日币", "日圆"}):
        return "JPY"
    if any(token in text for token in {"USD", "US$", "美元", "美金"}):
        return "USD"
    return ""


def _infer_client_account_currency(row: pd.Series) -> str:
    explicit_raw = row.get("币种")
    explicit_hint = _match_currency_hint(explicit_raw)
    if explicit_hint:
        return explicit_hint

    explicit = _normalize_currency_value(explicit_raw)
    if explicit:
        return explicit

    for column_name in ("渠道", "媒介", "母公司", "帐号 ID", "账号 ID", "账号ID"):
        hinted = _match_currency_hint(row.get(column_name))
        if hinted:
            return hinted

    # Historical client-account sheets often leave USD rows blank in the 币种 column.
    return "USD"


def _parse_month_text(text: str) -> Optional[str]:
    if not text:
        return None
    match = re.search(r"(20\d{2})\D{0,2}(\d{1,2})", str(text))
    if not match:
        return None
    year = int(match.group(1))
    month = int(match.group(2))
    if 2000 <= year <= 2099 and 1 <= month <= 12:
        return f"{year}-{month:02d}"
    return None


def _normalize_month_value(raw_value) -> Optional[str]:
    try:
        if pd.isna(raw_value):
            return None
    except Exception:
        pass

    def _fmt_month(year: int, month: int) -> Optional[str]:
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

        parsed = _parse_month_text(text)
        if parsed:
            return parsed

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

        # Excel serial date
        if 30000 <= rounded <= 70000:
            excel_dt = pd.to_datetime(rounded, unit="D", origin="1899-12-30", errors="coerce")
            if pd.notna(excel_dt):
                return _fmt_month(int(excel_dt.year), int(excel_dt.month))

    dt = pd.to_datetime(numeric_value, errors="coerce")
    if pd.notna(dt):
        return _fmt_month(int(dt.year), int(dt.month))
    return None


def _detect_row_month(row: pd.Series, default_month: Optional[str]) -> Optional[str]:
    if "月份归属" in row and pd.notna(row["月份归属"]):
        parsed = _normalize_month_value(row["月份归属"])
        if parsed:
            return parsed
    return default_month


def _extract_client_account_month(column_name: object) -> Optional[str]:
    text = str(column_name or "").strip()
    if not text or "消耗" not in text:
        return None
    return _parse_month_text(text)


def _is_client_account_sheet_name(sheet_name: str) -> bool:
    text = str(sheet_name or "")
    return any(marker in text for marker in _CLIENT_ACCOUNT_SHEET_MARKERS)


def _is_client_account_managed_sheet(sheet_name: str, df_sheet: pd.DataFrame) -> bool:
    if not _is_client_account_sheet_name(sheet_name):
        return False

    cols = set(df_sheet.columns.tolist())
    if not {"母公司", "媒介", "币种"}.issubset(cols):
        return False

    return any(_extract_client_account_month(column_name) for column_name in df_sheet.columns)


def _find_client_account_month_column(df_sheet: pd.DataFrame, target_month: Optional[str]) -> Optional[str]:
    if not target_month:
        return None

    for column_name in df_sheet.columns:
        if _extract_client_account_month(column_name) == target_month:
            return str(column_name)
    return None


def _build_client_account_managed_rows(
    df_sheet: pd.DataFrame,
    sheet_name: str,
    *,
    target_month: str,
    month_column: str,
) -> pd.DataFrame:
    monthly_consumption = pd.to_numeric(df_sheet.get(month_column), errors="coerce").fillna(0.0)
    currency_series = df_sheet.apply(_infer_client_account_currency, axis=1)

    out = pd.DataFrame(index=df_sheet.index)
    for column_name in ("媒介", "渠道", "帐号 ID", "母公司", "BD", "优化师", "优化师组", "币种"):
        if column_name in df_sheet.columns:
            out[column_name] = df_sheet[column_name]

    out["服务类型"] = "代投"
    out["代投消耗"] = monthly_consumption
    out["流水消耗"] = 0.0
    out["汇总纯花费"] = monthly_consumption
    out["币种"] = currency_series
    out["月份归属"] = target_month
    out[_COL_SOURCE_SHEET] = sheet_name
    out[_INTERNAL_SOURCE_ROW_COLUMN] = df_sheet.index.astype(int)
    out[_INTERNAL_TARGET_MONTH_COLUMN] = month_column
    return out


def _resolve_dst_column(df: pd.DataFrame) -> Optional[str]:
    for candidate in _DST_COLUMN_CANDIDATES:
        if candidate in df.columns:
            return candidate

    for column_name in df.columns:
        normalized = str(column_name).replace("\xa0", "").replace(" ", "")
        if normalized == _DST_COLUMN_NORMALIZED:
            return column_name

    for column_name in df.columns:
        normalized = _normalize_header_key(column_name)
        if any(alias in normalized for alias in _DST_COLUMN_FUZZY_ALIASES):
            return str(column_name)
    return None

def _load_consumption_data(consumption_path: str) -> pd.DataFrame:
    """Load consumption data from multi-sheet workbook."""
    workbook = pd.ExcelFile(consumption_path)
    frames = []

    for sheet in workbook.sheet_names:
        df_sheet = pd.read_excel(workbook, sheet_name=sheet)
        df_sheet = _standardize_headers(df_sheet)
        if df_sheet.empty:
            continue

        if "母公司" not in df_sheet.columns or "媒介" not in df_sheet.columns or "服务类型" not in df_sheet.columns:
            logger.info("Skipping non-consumption sheet: %s", sheet)
            continue

        currency_tag = _normalize_sheet_currency(sheet)
        df_local = df_sheet.copy()

        if currency_tag in {"USD", "JPY", "RMB", "EUR"}:
            df_local["币种"] = currency_tag
        elif currency_tag == "OTHER":
            if "币种" not in df_local.columns:
                raise ValueError("'其他币种' Sheet 缺少 '币种' 列，无法换汇")
            df_local["币种"] = df_local["币种"].apply(_normalize_currency_value)
        else:
            if "币种" in df_local.columns:
                df_local["币种"] = df_local["币种"].apply(_normalize_currency_value)
            else:
                df_local["币种"] = "USD"

        df_local["来源Sheet"] = sheet
        frames.append(df_local)

    if not frames:
        raise ValueError("未在上传文件中找到有效消耗数据 Sheet（需包含 母公司/媒介/服务类型 列）")

    return _standardize_headers(pd.concat(frames, ignore_index=True))


def _parse_hangseng_rmb_to_usd_context(exchange_context: dict) -> tuple[float, str, str]:
    hs = (exchange_context or {}).get("hangseng_today") or {}
    cny_tt_buy = _to_float(hs.get("cny_tt_buy"))
    usd_tt_sell = _to_float(hs.get("usd_tt_sell"))
    rate_date = str(hs.get("rate_date") or "")
    source = str(hs.get("source") or "hangseng_daily_snapshot")

    if cny_tt_buy <= 0 or usd_tt_sell <= 0:
        raise ValueError("缺少恒生可用的 CNY 电汇买入或 USD 电汇卖出汇率，无法执行 RMB->USD")

    return cny_tt_buy / usd_tt_sell, source, rate_date


def _parse_hangseng_eur_to_usd_context(exchange_context: dict) -> tuple[float, str, str]:
    hs = (exchange_context or {}).get("hangseng_today") or {}
    eur_tt_buy = _to_float(hs.get("eur_tt_buy"))
    usd_tt_sell = _to_float(hs.get("usd_tt_sell"))
    rate_date = str(hs.get("rate_date") or "")
    source = str(hs.get("source") or "hangseng_daily_snapshot")

    if eur_tt_buy <= 0 or usd_tt_sell <= 0:
        raise ValueError("缺少恒生可用的 EUR 电汇买入或 USD 电汇卖出汇率，无法执行 EUR->USD")

    return eur_tt_buy / usd_tt_sell, source, rate_date


def _parse_hangseng_jpy_to_usd_context(exchange_context: dict) -> tuple[float, str, str]:
    hs = (exchange_context or {}).get("hangseng_today") or {}
    jpy_tt_sell = _to_float(hs.get("jpy_tt_sell"))
    usd_tt_buy = _to_float(hs.get("usd_tt_buy"))
    rate_date = str(hs.get("rate_date") or "")
    source = str(hs.get("source") or "hangseng_daily_snapshot")

    if jpy_tt_sell <= 0 or usd_tt_buy <= 0:
        raise ValueError("缺少恒生可用的 JPY 电汇卖出或 USD 电汇买入汇率，无法执行 JPY->USD")

    return jpy_tt_sell / usd_tt_buy, source, rate_date


def _apply_exchange_rates(df: pd.DataFrame, exchange_context: dict, default_month: Optional[str]) -> pd.DataFrame:
    """Convert multi-currency consumption to USD and attach audit columns."""
    out = df.copy()

    out["原始代投消耗"] = out["代投消耗"].apply(_to_float) if "代投消耗" in out.columns else 0.0
    out["原始流水消耗"] = out["流水消耗"].apply(_to_float) if "流水消耗" in out.columns else 0.0

    out["原始汇总纯花费"] = out[_COL_NET_SPEND].apply(_to_float) if _COL_NET_SPEND in out.columns else 0.0

    rates = []
    sources = []
    rate_dates = []

    for _, row in out.iterrows():
        currency = _normalize_currency_value(row.get("币种")) or "USD"

        if currency == "USD":
            fx_rate = 1.0
            src = "identity_usd"
            dt = ""
        elif currency == "RMB":
            fx_rate, src, dt = _parse_hangseng_rmb_to_usd_context(exchange_context)
        elif currency == "EUR":
            fx_rate, src, dt = _parse_hangseng_eur_to_usd_context(exchange_context)
        elif currency == "JPY":
            # Keep month parse side effect compatible for data auditing.
            _detect_row_month(row, default_month)
            fx_rate, src, dt = _parse_hangseng_jpy_to_usd_context(exchange_context)
        else:
            raise ValueError(f"暂不支持币种 {currency} 自动换汇，请先转为 USD/RMB/JPY/EUR 或扩展汇率规则")

        rates.append(fx_rate)
        sources.append(src)
        rate_dates.append(dt)

    out["换汇汇率"] = rates
    out["汇率来源"] = sources
    out["汇率日期"] = rate_dates

    out["代投消耗"] = out["原始代投消耗"] * out["换汇汇率"]
    out["流水消耗"] = out["原始流水消耗"] * out["换汇汇率"]

    if _COL_NET_SPEND in out.columns:
        out[_COL_NET_SPEND] = out["原始汇总纯花费"] * out["换汇汇率"]
    out["换汇后代投消耗USD"] = out["代投消耗"].round(6)
    out["换汇后流水消耗USD"] = out["流水消耗"].round(6)

    return out


def _load_consumption_data(
    consumption_path: str,
    *,
    calculation_date: Optional[str],
) -> tuple[pd.DataFrame, dict]:
    """Load consumption data from multi-sheet workbook."""
    workbook = pd.ExcelFile(consumption_path)
    frames = []
    included_sheet_names: list[str] = []
    client_account_sheets: dict[str, dict] = {}
    target_month = _parse_month_text(calculation_date or "")

    for sheet in workbook.sheet_names:
        df_sheet = pd.read_excel(workbook, sheet_name=sheet)
        raw_sheet_df = df_sheet.copy()
        df_sheet = _standardize_headers(df_sheet)
        df_sheet = _populate_consumption_columns(df_sheet)
        if df_sheet.empty:
            continue

        if _is_client_account_managed_sheet(sheet, df_sheet):
            month_column = _find_client_account_month_column(df_sheet, target_month)
            if not target_month or not month_column:
                raise ValueError(
                    f"{sheet} Sheet 未找到与计算月份匹配的消耗列，当前计算月份: {calculation_date or '未知'}"
                )

            frames.append(
                _build_client_account_managed_rows(
                    df_sheet,
                    sheet,
                    target_month=target_month,
                    month_column=month_column,
                )
            )
            included_sheet_names.append(sheet)
            client_account_sheets[sheet] = {
                "original_df": raw_sheet_df,
                "target_month_column": month_column,
            }
            continue

        if "母公司" not in df_sheet.columns or "媒介" not in df_sheet.columns or "服务类型" not in df_sheet.columns:
            logger.info("Skipping non-consumption sheet: %s", sheet)
            continue

        currency_tag = _normalize_sheet_currency(sheet)
        df_local = df_sheet.copy()

        if currency_tag in {"USD", "JPY", "RMB", "EUR"}:
            df_local["币种"] = currency_tag
        elif currency_tag == "OTHER":
            if "币种" not in df_local.columns:
                raise ValueError("'其他币种' Sheet 缺少 '币种' 列，无法换汇")
            df_local["币种"] = df_local["币种"].apply(_normalize_currency_value)
        else:
            if "币种" in df_local.columns:
                df_local["币种"] = df_local["币种"].apply(_normalize_currency_value)
            else:
                df_local["币种"] = "USD"

        df_local[_COL_SOURCE_SHEET] = sheet
        frames.append(df_local)
        included_sheet_names.append(sheet)

    if not frames:
        raise ValueError("未在上传文件中找到有效消费数据 Sheet（需包含 母公司/媒介/服务类型 列）")

    return _populate_consumption_columns(_standardize_headers(pd.concat(frames, ignore_index=True))), {
        "sheet_order": workbook.sheet_names,
        "included_sheet_names": included_sheet_names,
        "client_account_sheets": client_account_sheets,
    }


def _build_client_account_result_column_names(month_column: str) -> tuple[str, str, str, str]:
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


def _build_client_account_output_sheet(
    original_df: pd.DataFrame,
    result_rows: pd.DataFrame,
    *,
    target_month_column: str,
) -> pd.DataFrame:
    output_df = original_df.copy()
    if target_month_column not in output_df.columns:
        return output_df

    result_map = result_rows.set_index(_INTERNAL_SOURCE_ROW_COLUMN)
    service_col, fixed_col, fx_col, usd_col = _build_client_account_result_column_names(target_month_column)
    service_series = output_df.index.to_series().map(result_map["服务费"]) if "服务费" in result_map else None
    fixed_series = output_df.index.to_series().map(result_map["固定服务费"]) if "固定服务费" in result_map else None
    fx_series = output_df.index.to_series().map(result_map["换汇汇率"]) if "换汇汇率" in result_map else None
    usd_series = (
        output_df.index.to_series().map(result_map["换汇后代投消耗USD"])
        if "换汇后代投消耗USD" in result_map
        else None
    )

    insert_at = output_df.columns.get_loc(target_month_column) + 1
    output_df.insert(insert_at, service_col, service_series)
    output_df.insert(insert_at + 1, fixed_col, fixed_series)
    output_df.insert(insert_at + 2, fx_col, fx_series)
    output_df.insert(insert_at + 3, usd_col, usd_series)
    return output_df


def _build_hidden_result_sheet(df: pd.DataFrame) -> pd.DataFrame:
    return df.drop(
        columns=[
            _INTERNAL_SOURCE_ROW_COLUMN,
            _INTERNAL_TARGET_MONTH_COLUMN,
        ],
        errors="ignore",
    )


def _build_client_account_output_sheet_v2(
    original_df: pd.DataFrame,
    result_rows: pd.DataFrame,
    *,
    target_month_column: str,
) -> pd.DataFrame:
    output_df = original_df.copy()
    if target_month_column not in output_df.columns:
        return output_df

    result_map = result_rows.set_index(_INTERNAL_SOURCE_ROW_COLUMN)
    service_col, fixed_col, fx_col, usd_col = _build_client_account_result_column_names(target_month_column)
    service_series = output_df.index.to_series().map(result_map[_COL_SERVICE_FEE]) if _COL_SERVICE_FEE in result_map else None
    fixed_series = output_df.index.to_series().map(result_map[_COL_FIXED_SERVICE_FEE]) if _COL_FIXED_SERVICE_FEE in result_map else None
    fx_series = output_df.index.to_series().map(result_map["换汇汇率"]) if "换汇汇率" in result_map else None
    usd_series = (
        output_df.index.to_series().map(result_map["换汇后代投消耗USD"])
        if "换汇后代投消耗USD" in result_map
        else None
    )
    currency_series = (
        output_df.index.to_series().map(result_map["币种"])
        if "币种" in result_map
        else pd.Series("USD", index=output_df.index, dtype="object")
    )
    normalized_currency = currency_series.apply(_normalize_currency_value).replace("", "USD")
    show_fx_columns = bool((normalized_currency != "USD").any())

    insert_at = output_df.columns.get_loc(target_month_column) + 1
    output_df.insert(insert_at, service_col, service_series)
    output_df.insert(insert_at + 1, fixed_col, fixed_series)
    if show_fx_columns:
        non_usd_mask = normalized_currency != "USD"
        if isinstance(fx_series, pd.Series):
            fx_series = fx_series.where(non_usd_mask)
        if isinstance(usd_series, pd.Series):
            usd_series = usd_series.where(non_usd_mask)
        output_df.insert(insert_at + 2, fx_col, fx_series)
        output_df.insert(insert_at + 3, usd_col, usd_series)
    return output_df


def _build_visible_result_sheet(sheet_rows: pd.DataFrame) -> pd.DataFrame:
    visible_df = sheet_rows.drop(
        columns=[
            _COL_SOURCE_SHEET,
            _INTERNAL_SOURCE_ROW_COLUMN,
            _INTERNAL_TARGET_MONTH_COLUMN,
        ],
        errors="ignore",
    ).copy()
    if visible_df.empty or "币种" not in visible_df.columns:
        return visible_df

    currency_series = visible_df["币种"].apply(_normalize_currency_value).replace("", "USD")
    usd_mask = currency_series == "USD"
    if bool(usd_mask.all()):
        return visible_df.drop(columns=list(_VISIBLE_FX_AUDIT_COLUMNS), errors="ignore")

    if bool(usd_mask.any()):
        for column_name in _VISIBLE_FX_AUDIT_COLUMNS:
            if column_name in visible_df.columns:
                visible_df.loc[usd_mask, column_name] = None
    return visible_df


def _write_result_workbook(output_path: str, df: pd.DataFrame, workbook_meta: dict) -> None:
    client_account_sheets = workbook_meta.get("client_account_sheets", {})
    included_sheet_set = set(workbook_meta.get("included_sheet_names", []))
    visible_sheet_names = [
        sheet_name
        for sheet_name in workbook_meta.get("sheet_order", [])
        if sheet_name in included_sheet_set
    ]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name in visible_sheet_names:
            sheet_rows = df[df[_COL_SOURCE_SHEET] == sheet_name].copy()

            if sheet_name in client_account_sheets:
                visible_df = _build_client_account_output_sheet_v2(
                    client_account_sheets[sheet_name]["original_df"],
                    sheet_rows,
                    target_month_column=client_account_sheets[sheet_name]["target_month_column"],
                )
                visible_df.to_excel(writer, index=False, sheet_name=sheet_name)
                continue

            visible_df = _build_visible_result_sheet(sheet_rows)
            visible_df.to_excel(writer, index=False, sheet_name=sheet_name)

        hidden_df = _build_hidden_result_sheet(df)
        hidden_df.to_excel(writer, index=False, sheet_name=_HIDDEN_RESULT_SHEET_NAME)
        writer.book[_HIDDEN_RESULT_SHEET_NAME].sheet_state = "hidden"


def calculate_service_fees(
    consumption_path: str,
    contract_path: str = None,
    output_path: str = None,
    use_db: bool = False,
    calculation_date: str = None,
    **kwargs,
) -> str:
    """Calculate service fees and output enriched workbook."""
    if not calculation_date:
        consumption_filename = Path(consumption_path).stem
        calculation_date = extract_date_from_filename(consumption_filename)
        if calculation_date:
            logger.info("Detected calculation date from filename: %s", calculation_date)

    default_month = _parse_month_text(calculation_date or "")

    feishu_config = kwargs.get("feishu_config")
    contract_terms = {}

    if feishu_config:
        contract_terms = load_contract_terms_from_feishu(
            feishu_config["app_id"],
            feishu_config["app_secret"],
            feishu_config["app_token"],
        )

    if not contract_terms:
        if use_db:
            contract_terms = load_contract_terms_from_db()
        else:
            contract_terms = load_contract_terms(contract_path)

    logger.info("Loaded %s contract clauses", len(contract_terms))

    df_raw, workbook_meta = _load_consumption_data(
        consumption_path,
        calculation_date=calculation_date,
    )
    logger.info("Loaded %s consumption rows", len(df_raw))

    exchange_context = kwargs.get("exchange_context") or {}
    df = _apply_exchange_rates(df_raw, exchange_context, default_month)
    df = _standardize_headers(df)
    df = _populate_consumption_columns(df)

    coupon_idx = df.columns.get_loc(_COL_COUPON) if _COL_COUPON in df.columns else len(df.columns)

    combined_consumption: dict[tuple[str, str], float] = {}
    for customer in df["母公司"].dropna().unique():
        customer_str = str(customer).strip()
        clause = contract_terms.get(customer_str, "无")

        if "合计" in str(clause):
            customer_df = df[df["母公司"] == customer]
            for service_type in ["代投", "流水"]:
                col = "代投消耗" if service_type == "代投" else "流水消耗"
                total = pd.to_numeric(customer_df[col], errors="coerce").fillna(0).sum() if col in customer_df.columns else 0
                combined_consumption[(customer_str, service_type)] = total if pd.notna(total) else 0

    service_fees = []
    fixed_fees: list[float | None] = [None] * len(df)
    customer_fixed_fee_filled = set()
    unsupported_service_type_logged: set[str] = set()
    from billing.clause_parser import MEDIA_KEYWORDS

    for row_idx, (_, row) in enumerate(df.iterrows()):
        customer = row["母公司"]
        media = row["媒介"]
        raw_service_type = str(row.get("服务类型") or "").strip()
        service_type = _normalize_service_type(raw_service_type)
        is_managed_service = _is_managed_service_type(service_type)

        customer_str = str(customer).strip() if pd.notna(customer) else ""
        clause = contract_terms.get(customer_str, "无")

        liushui_consumption = _to_float(row.get("流水消耗"))
        daitou_consumption = _to_float(row.get("代投消耗"))
        if (
            service_type not in {"流水", "代投", "代投+流水"}
            and (abs(liushui_consumption) > 1e-9 or abs(daitou_consumption) > 1e-9)
        ):
            warn_key = raw_service_type or "<empty>"
            if warn_key not in unsupported_service_type_logged:
                logger.warning(
                    "Unsupported service type '%s' (normalized '%s'); fee defaults to 0 unless covered by custom rules",
                    raw_service_type,
                    service_type,
                )
                unsupported_service_type_logged.add(warn_key)

        fee = 0.0
        fixed = 0.0

        combined_liushui = combined_consumption.get((customer_str, "流水"))
        combined_daitou = combined_consumption.get((customer_str, "代投"))

        if service_type == "流水":
            rate, fixed = parse_fee_clause(
                clause,
                media,
                "流水",
                liushui_consumption,
                combined_liushui,
                calculation_date,
                client_name=customer_str,
            )
            fee = liushui_consumption * _to_float(rate)
            fixed = 0.0

        elif service_type == "代投":
            rate, fixed = parse_fee_clause(
                clause,
                media,
                "代投",
                daitou_consumption,
                combined_daitou,
                calculation_date,
                client_name=customer_str,
            )
            fee = daitou_consumption * _to_float(rate)
            fixed = _to_float(fixed)

        elif service_type == "代投+流水":
            liushui_rate, _liushui_fixed = parse_fee_clause(
                clause,
                media,
                "流水",
                liushui_consumption,
                combined_liushui,
                calculation_date,
                client_name=customer_str,
            )
            daitou_rate, daitou_fixed = parse_fee_clause(
                clause,
                media,
                "代投",
                daitou_consumption,
                combined_daitou,
                calculation_date,
                client_name=customer_str,
            )
            fee = liushui_consumption * _to_float(liushui_rate) + daitou_consumption * _to_float(daitou_rate)
            fixed = _to_float(daitou_fixed)

        fee = _to_float(fee)
        fixed = _to_float(fixed)
        fee, fixed = apply_post_overrides(customer_str, fee, fixed)
        if not is_managed_service:
            fixed = 0.0

        waiver_match = re.search(r'合计消耗\s*[*×]?\s*(\d+(?:\.\d+)?)\s*%\s*[大超]于(?:等于)?\s*(\d+)', str(clause))
        if waiver_match and fixed > 0:
            waiver_rate = float(waiver_match.group(1)) / 100.0
            waiver_threshold = float(waiver_match.group(2))
            
            if service_type == "代投+流水":
                total_for_waiver = combined_consumption.get((customer_str, "代投"), 0.0) + combined_consumption.get((customer_str, "流水"), 0.0)
            else:
                total_for_waiver = combined_consumption.get((customer_str, service_type), 0.0)
                
            if total_for_waiver * waiver_rate >= waiver_threshold:
                fixed = 0.0

        service_fees.append(_round2(fee) if fee > 0 else None)
        if is_managed_service and daitou_consumption > 1e-9 and fixed > 0:
            contains_ge_han = any(kw in str(clause) for kw in ["含", "各", "单渠道", "单个渠道", "每个"])
            contains_heji = any(kw in str(clause) for kw in ["合计", "总体", "一共"])
            media_aliases = MEDIA_KEYWORDS.get(media, [media])
            media_in_clause = any(a.lower() in str(clause).lower() for a in media_aliases)
            # Explicit per-media markers such as "各1000" must still count per
            # media even when the clause also contains aggregate waiver text
            # like "合计消耗*7%大于等于3000".
            is_per_media = contains_ge_han or (media_in_clause and not contains_heji)
            dedup_key = (customer_str, media) if is_per_media else customer_str

            if dedup_key not in customer_fixed_fee_filled:
                fixed_fees[row_idx] = _round2(fixed)
                customer_fixed_fee_filled.add(dedup_key)

    if "服务费" in df.columns:
        df["服务费"] = service_fees
    else:
        df.insert(coupon_idx, "服务费", service_fees)
        coupon_idx += 1

    if "固定服务费" in df.columns:
        df["固定服务费"] = fixed_fees
    else:
        df.insert(coupon_idx, "固定服务费", fixed_fees)

    dst_col = _resolve_dst_column(df)

    def safe_sum(row):
        # Business invariant: totals are based on converted split spend fields first.
        converted_spend = _to_float(row.get("代投消耗")) + _to_float(row.get("流水消耗"))
        if abs(converted_spend) > 1e-9:
            net_spend = converted_spend
        else:
            raw_total = _to_float(row.get("汇总纯花费"))
            fx_rate = _to_float(row.get("换汇汇率")) or 1.0
            net_spend = raw_total * fx_rate

        values = [
            net_spend,
            _to_float(row["服务费"]) if "服务费" in row else 0,
            _to_float(row["固定服务费"]) if "固定服务费" in row else 0,
            _to_float(row[_COL_COUPON]) if _COL_COUPON in row else 0,
            _to_float(row.get(dst_col)) if dst_col else 0,
        ]
        return _round2(sum(values))

    df["汇总"] = df.apply(safe_sum, axis=1)

    if output_path is None:
        input_path = Path(consumption_path)
        output_path = input_path.parent / f"{input_path.stem}_results{input_path.suffix}"

    _write_result_workbook(str(output_path), df, workbook_meta)
    logger.info("Calculation completed, output saved to %s", output_path)
    return str(output_path)
