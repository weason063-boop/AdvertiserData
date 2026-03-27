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


def _round2(value: float) -> float:
    """Standard half-up rounding to 2 decimal places (财务四舍五入)."""
    try:
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except Exception:
        return round(float(value), 2)


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


def _normalize_sheet_currency(sheet_name: str) -> Optional[str]:
    name = str(sheet_name or "").strip().lower().replace(" ", "")
    if name in {"usd", "美元", "us$"}:
        return "USD"
    if name in {"rmb", "cny", "人民币"}:
        return "RMB"
    if name in {"jpy", "日元", "日币"}:
        return "JPY"
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
    if text in {"JPY", "日元", "日币", "日圆"}:
        return "JPY"
    if text in {"USD", "美元", "US$"}:
        return "USD"
    return text


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


def _load_consumption_data(consumption_path: str) -> pd.DataFrame:
    """Load consumption data from multi-sheet workbook."""
    workbook = pd.ExcelFile(consumption_path)
    frames = []

    for sheet in workbook.sheet_names:
        df_sheet = pd.read_excel(workbook, sheet_name=sheet)
        if df_sheet.empty:
            continue

        if "母公司" not in df_sheet.columns or "媒介" not in df_sheet.columns or "服务类型" not in df_sheet.columns:
            logger.info("Skipping non-consumption sheet: %s", sheet)
            continue

        currency_tag = _normalize_sheet_currency(sheet)
        df_local = df_sheet.copy()

        if currency_tag in {"USD", "JPY", "RMB"}:
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

    return pd.concat(frames, ignore_index=True)


def _parse_hangseng_rmb_to_usd_context(exchange_context: dict) -> tuple[float, str, str]:
    hs = (exchange_context or {}).get("hangseng_today") or {}
    cny_tt_buy = _to_float(hs.get("cny_tt_buy"))
    usd_tt_sell = _to_float(hs.get("usd_tt_sell"))
    rate_date = str(hs.get("rate_date") or "")
    source = str(hs.get("source") or "hangseng_daily_snapshot")

    if cny_tt_buy <= 0 or usd_tt_sell <= 0:
        raise ValueError("缺少恒生可用的 CNY 电汇买入或 USD 电汇卖出汇率，无法执行 RMB->USD")

    return cny_tt_buy / usd_tt_sell, source, rate_date


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
        elif currency == "JPY":
            # Keep month parse side effect compatible for data auditing.
            _detect_row_month(row, default_month)
            fx_rate, src, dt = _parse_hangseng_jpy_to_usd_context(exchange_context)
        else:
            raise ValueError(f"暂不支持币种 {currency} 自动换汇，请先转为 USD/RMB/JPY 或扩展汇率规则")

        rates.append(fx_rate)
        sources.append(src)
        rate_dates.append(dt)

    out["换汇汇率"] = rates
    out["汇率来源"] = sources
    out["汇率日期"] = rate_dates

    out["代投消耗"] = out["原始代投消耗"] * out["换汇汇率"]
    out["流水消耗"] = out["原始流水消耗"] * out["换汇汇率"]

    out["换汇后代投消耗USD"] = out["代投消耗"].round(6)
    out["换汇后流水消耗USD"] = out["流水消耗"].round(6)

    return out


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

    df_raw = _load_consumption_data(consumption_path)
    logger.info("Loaded %s consumption rows", len(df_raw))

    exchange_context = kwargs.get("exchange_context") or {}
    df = _apply_exchange_rates(df_raw, exchange_context, default_month)

    coupon_idx = df.columns.get_loc("Coupon") if "Coupon" in df.columns else len(df.columns)

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
    fixed_fees = []
    customer_fixed_fee_filled = set()

    for _, row in df.iterrows():
        customer = row["母公司"]
        media = row["媒介"]
        service_type = str(row.get("服务类型") or "").strip()

        customer_str = str(customer).strip() if pd.notna(customer) else ""
        clause = contract_terms.get(customer_str, "无")

        liushui_consumption = _to_float(row.get("流水消耗"))
        daitou_consumption = _to_float(row.get("代投消耗"))

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
            fixed = _to_float(fixed)

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
            liushui_rate, liushui_fixed = parse_fee_clause(
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
            fixed = _to_float(liushui_fixed) + _to_float(daitou_fixed)

        fee = _to_float(fee)
        fixed = _to_float(fixed)
        fee, fixed = apply_post_overrides(customer_str, fee, fixed)

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

        is_per_media = any(kw in str(clause) for kw in ["含", "各"])
        dedup_key = (customer_str, media) if is_per_media else customer_str

        if fixed > 0 and dedup_key not in customer_fixed_fee_filled:
            fixed_fees.append(_round2(fixed))
            customer_fixed_fee_filled.add(dedup_key)
        else:
            fixed_fees.append(None)

    if "服务费" in df.columns:
        df["服务费"] = service_fees
    else:
        df.insert(coupon_idx, "服务费", service_fees)
        coupon_idx += 1

    if "固定服务费" in df.columns:
        df["固定服务费"] = fixed_fees
    else:
        df.insert(coupon_idx, "固定服务费", fixed_fees)

    dst_col = "监管运营费用/数字服务税(DST)\xa0"

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
            _to_float(row["Coupon"]) if "Coupon" in row else 0,
            _to_float(row[dst_col]) if dst_col in row else 0,
        ]
        return _round2(sum(values))

    df["汇总"] = df.apply(safe_sum, axis=1)

    if output_path is None:
        input_path = Path(consumption_path)
        output_path = input_path.parent / f"{input_path.stem}_results{input_path.suffix}"

    df.to_excel(output_path, index=False)
    logger.info("Calculation completed, output saved to %s", output_path)
    return str(output_path)
