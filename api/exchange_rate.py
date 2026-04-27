import logging
import re
import time
from datetime import datetime
from typing import Dict, List

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

logger = logging.getLogger(__name__)

# In-memory cache
_RATE_CACHE = {
    "hangseng": {
        "data": [],
        "timestamp": None,
    }
}
_CACHE_TIMEOUT = 3600  # seconds

_CURRENCY_CODE_PATTERN = re.compile(r"\(([A-Z]{3})\)")


CURRENCY_NAME_MAP = {
    "USD": "美元 (USD)",
    "CNY": "人民币 (CNY)",
    "HKD": "港币 (HKD)",
    "AUD": "澳元 (AUD)",
    "CAD": "加元 (CAD)",
    "EUR": "欧元 (EUR)",
    "GBP": "英镑 (GBP)",
    "JPY": "日圆 (JPY)",
    "NZD": "纽元 (NZD)",
    "SGD": "新加坡元 (SGD)",
    "CHF": "瑞士法郎 (CHF)",
    "THB": "泰铢 (THB)",
    "ZAR": "南非兰特 (ZAR)",
    "SEK": "瑞典克朗 (SEK)",
    "DKK": "丹麦克朗 (DKK)",
    "NOK": "挪威克朗 (NOK)",
}


def _extract_currency_code(currency_text: str) -> str:
    text = str(currency_text or "").upper()
    match = _CURRENCY_CODE_PATTERN.search(text)
    if match:
        return match.group(1)

    if "RMB" in text:
        return "CNY"

    for code in ("CNY", "USD", "JPY", "EUR"):
        if code in text:
            return code
    return ""


def _extract_currency_code_from_row(row: Dict) -> str:
    code = str((row or {}).get("code") or "").strip().upper()
    if re.fullmatch(r"[A-Z]{3}", code):
        return code
    return _extract_currency_code(str((row or {}).get("currency") or ""))


def _to_rate_float(value) -> float | None:
    try:
        text = str(value or "").strip().replace(",", "")
        if not text or text == "-":
            return None
        return float(text)
    except Exception:
        return None


def _has_required_hangseng_fields(rows: List[Dict]) -> bool:
    cny_tt_buy = None
    eur_tt_buy = None
    usd_tt_buy = None
    usd_tt_sell = None
    jpy_tt_sell = None

    for row in rows or []:
        if not isinstance(row, dict):
            continue
        code = _extract_currency_code_from_row(row)
        if code == "CNY":
            cny_tt_buy = _to_rate_float(row.get("tt_buy"))
        elif code == "EUR":
            eur_tt_buy = _to_rate_float(row.get("tt_buy"))
        elif code == "USD":
            usd_tt_buy = _to_rate_float(row.get("tt_buy"))
            usd_tt_sell = _to_rate_float(row.get("tt_sell"))
        elif code == "JPY":
            jpy_tt_sell = _to_rate_float(row.get("tt_sell"))

    required = (cny_tt_buy, eur_tt_buy, usd_tt_buy, usd_tt_sell, jpy_tt_sell)
    return all(value is not None and value > 0 for value in required)


def get_cfets_rates() -> List[Dict]:
    """Fetch RMB central parity from CFETS."""
    try:
        current_date = datetime.now().strftime("%Y-%m-%d")
        url = (
            "https://www.chinamoney.com.cn/ags/ms/cm-u-bk-ccpr/CcprHisNew"
            f"?startDate={current_date}&endDate={current_date}"
        )
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/91.0.4472.124 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()

        rates = []
        if "records" in data and data["records"]:
            values = data["records"][0].get("values") or []
            if values:
                usd_val = float(values[0])
                if 6.0 < usd_val < 8.0:
                    rates.append(
                        {
                            "currency": "美元 (USD)",
                            "middle_rate": usd_val,
                            "pub_time": datetime.now().strftime("%Y-%m-%d"),
                        }
                    )
        return rates
    except Exception as exc:
        logger.warning("CFETS API failed: %s", exc)
        return []


def _safe_pick(values: list[str], idx: int) -> str:
    if 0 <= idx < len(values):
        return values[idx].strip()
    return "-"


def _normalize_jpy_quote_if_needed(
    code: str,
    currency_raw: str,
    tt_buy: str,
    tt_sell: str,
    notes_buy: str,
    notes_sell: str,
) -> tuple[str, str, str, str]:
    """
    Hang Seng JPY row is often quoted per 1,000 JPY.
    Normalize to per-1 JPY for downstream formulas.
    """
    is_per_1000 = code == "JPY" and (
        "1000" in currency_raw.replace(",", "") or "1,000" in currency_raw
    )
    if not is_per_1000:
        return tt_buy, tt_sell, notes_buy, notes_sell

    def _scale(text: str) -> str:
        value = _to_rate_float(text)
        if value is None:
            return ""
        return f"{value / 1000.0:.4f}"

    return _scale(tt_buy), _scale(tt_sell), _scale(notes_buy), _scale(notes_sell)


def get_hangseng_rates_selenium() -> List[Dict]:
    """Fetch Hang Seng FX board rates via Selenium."""
    logger.info("Starting Selenium scraping for Hang Seng rates (all currencies)")

    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )

    driver = None
    results: list[dict] = []

    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        url = "https://www.hangseng.com/zh-cn/personal/banking/rates/foreign-exchange-rates/"
        driver.get(url)

        try:
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "table"))
            )
        except Exception:
            logger.warning("Timeout waiting for Hang Seng table")

        time.sleep(3)
        rows = driver.find_elements(By.CSS_SELECTOR, "table tr")
        logger.info("Hang Seng scraper found %s rows", len(rows))

        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) < 4:
                continue

            try:
                values = [col.text.strip() for col in cols]
                currency_raw = values[0].strip() if values else ""
                if not currency_raw or "货币" in currency_raw or "Currency" in currency_raw:
                    continue

                # New page layout:
                # [货币, 代号, 电汇买入, 电汇卖出, 现钞买入, 现钞卖出]
                code_cell = values[1].strip().upper() if len(values) > 1 else ""
                has_code_col = bool(re.fullmatch(r"[A-Z]{3}", code_cell))
                code = code_cell if has_code_col else ""

                if has_code_col:
                    tt_buy = _safe_pick(values, 2)
                    tt_sell = _safe_pick(values, 3)
                    notes_buy = _safe_pick(values, 4)
                    notes_sell = _safe_pick(values, 5)
                else:
                    tt_buy = _safe_pick(values, 1)
                    tt_sell = _safe_pick(values, 2)
                    notes_buy = _safe_pick(values, 3)
                    notes_sell = _safe_pick(values, 4)

                has_data = any(x and x != "-" for x in [tt_buy, tt_sell, notes_buy, notes_sell])
                if not has_data:
                    continue

                if not code:
                    code_match = re.search(r"\(([A-Z]{3})\)", currency_raw)
                    if code_match:
                        code = code_match.group(1)

                tt_buy, tt_sell, notes_buy, notes_sell = _normalize_jpy_quote_if_needed(
                    code,
                    currency_raw,
                    tt_buy,
                    tt_sell,
                    notes_buy,
                    notes_sell,
                )

                final_name = CURRENCY_NAME_MAP.get(code, currency_raw) if code else currency_raw
                results.append(
                    {
                        "currency": final_name,
                        "code": code,
                        "tt_buy": tt_buy if tt_buy != "-" else "",
                        "tt_sell": tt_sell if tt_sell != "-" else "",
                        "notes_buy": notes_buy if notes_buy != "-" else "",
                        "notes_sell": notes_sell if notes_sell != "-" else "",
                        "pub_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
            except Exception as row_err:
                logger.debug("Error parsing Hang Seng row: %s", row_err)
                continue

        if not results:
            logger.warning("No structured table data found. Falling back to regex parsing")
            body_text = driver.find_element(By.TAG_NAME, "body").text
            parsed_rates: dict[str, dict] = {}

            for line in body_text.split("\n"):
                m_buy = re.search(r"买入 \(([A-Z]+)\)\s+([\d\.]+|-)", line)
                if m_buy:
                    code = m_buy.group(1)
                    price = m_buy.group(2)
                    cn_name = CURRENCY_NAME_MAP.get(code, f"{code} ({code})")
                    if code not in parsed_rates:
                        parsed_rates[code] = {
                            "currency": cn_name,
                            "code": code,
                            "tt_buy": price,
                            "tt_sell": "-",
                            "notes_buy": "-",
                            "notes_sell": "-",
                        }
                    elif parsed_rates[code]["notes_buy"] == "-":
                        parsed_rates[code]["notes_buy"] = price

                m_sell = re.search(r"卖出 \(([A-Z]+)\)\s+([\d\.]+|-)", line)
                if m_sell:
                    code = m_sell.group(1)
                    price = m_sell.group(2)
                    if code in parsed_rates:
                        if parsed_rates[code]["tt_sell"] == "-":
                            parsed_rates[code]["tt_sell"] = price
                        elif parsed_rates[code]["notes_sell"] == "-":
                            parsed_rates[code]["notes_sell"] = price

            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in parsed_rates.values():
                item["pub_time"] = now_text
                results.append(item)

    except Exception as exc:
        logger.error("Selenium scraping failed: %s", exc)
    finally:
        if driver:
            driver.quit()

    return results


def get_hangseng_rates_mock() -> List[Dict]:
    """Fallback mock data."""
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mock_data = [
        {"currency": "美元 (USD)", "code": "USD", "tt_buy": "7.7930", "tt_sell": "7.8370", "notes_buy": "7.7380", "notes_sell": "7.8620"},
        {"currency": "人民币 (CNY)", "code": "CNY", "tt_buy": "1.1193", "tt_sell": "1.1327", "notes_buy": "1.1093", "notes_sell": "1.1367"},
        {"currency": "澳元 (AUD)", "code": "AUD", "tt_buy": "5.4480", "tt_sell": "5.5220", "notes_buy": "5.3890", "notes_sell": "5.5450"},
        {"currency": "加元 (CAD)", "code": "CAD", "tt_buy": "5.6920", "tt_sell": "5.7610", "notes_buy": "5.6630", "notes_sell": "5.8250"},
        {"currency": "欧元 (EUR)", "code": "EUR", "tt_buy": "9.1840", "tt_sell": "9.2860", "notes_buy": "9.1080", "notes_sell": "9.3380"},
        {"currency": "英镑 (GBP)", "code": "GBP", "tt_buy": "10.6510", "tt_sell": "10.7700", "notes_buy": "10.5120", "notes_sell": "10.9090"},
        {"currency": "日圆 (JPY)", "code": "JPY", "tt_buy": "0.0495", "tt_sell": "0.0502", "notes_buy": "0.0490", "notes_sell": "0.0506"},
    ]
    for item in mock_data:
        item["pub_time"] = f"{current_time} (模拟)"
        item["source"] = "hangseng_mock"
    return mock_data


def get_hangseng_rates() -> List[Dict]:
    """
    Fetch Hang Seng board rates.
    Strategy: cache -> selenium live -> mock fallback.
    """
    global _RATE_CACHE

    cached = _RATE_CACHE["hangseng"]
    if cached["data"] and cached["timestamp"]:
        elapsed = (datetime.now() - cached["timestamp"]).total_seconds()
        if elapsed < _CACHE_TIMEOUT and _has_required_hangseng_fields(cached["data"]):
            logger.debug("Returning cached Hang Seng rates (%.0fs old)", elapsed)
            return cached["data"]
        if elapsed < _CACHE_TIMEOUT:
            logger.warning("Ignoring incomplete cached Hang Seng live rates")

    try:
        data = get_hangseng_rates_selenium()
        if data and _has_required_hangseng_fields(data):
            now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            for item in data:
                item["pub_time"] = now_text
                item["source"] = "hangseng_live"

            _RATE_CACHE["hangseng"] = {
                "data": data,
                "timestamp": datetime.now(),
            }
            return data

        if data:
            logger.warning("Live Hang Seng payload is incomplete, falling back to mock data")
    except Exception as exc:
        logger.error("Selenium fetch failed: %s", exc)

    logger.info("Using fallback mock data for Hang Seng")
    return get_hangseng_rates_mock()


def get_all_rates() -> Dict[str, List[Dict]]:
    return {
        "cfets": get_cfets_rates(),
        "hangseng": get_hangseng_rates(),
    }
