# -*- coding: utf-8 -*-
"""
鏈嶅姟璐硅嚜鍔ㄨ绠楀伐鍏?鈥?鍏煎灞?
鏈枃浠朵负鍘嗗彶鍏ュ彛鐐癸紝瀹為檯閫昏緫宸叉媶鍒嗚嚦 billing/ 鍖咃細
  - billing.clause_parser    鈥?鏉℃瑙ｆ瀽
  - billing.client_overrides 鈥?瀹㈡埛鐗规畩瑙勫垯
  - billing.contract_loader  鈥?鍚堝悓鍔犺浇 (椋炰功/DB/Excel)
  - billing.fee_engine       鈥?涓昏绠楁祦绋?
鎵€鏈?public API 閫氳繃姝ゆ枃浠?re-export锛屼繚璇佺幇鏈?import 鍏煎銆?"""

# Re-export all public APIs for backward compatibility
from pathlib import Path

from billing.fee_engine import calculate_service_fees  # noqa: F401
from billing.clause_parser import parse_fee_clause, extract_applicable_clause  # noqa: F401
from billing.contract_loader import (  # noqa: F401
    load_contract_terms,
    load_contract_terms_from_db,
    load_contract_terms_from_feishu,
    extract_date_from_filename,
)
from billing.client_overrides import (  # noqa: F401
    load_client_overrides as _load_client_overrides,
    apply_pre_overrides as _apply_pre_overrides,
    apply_post_overrides as _apply_post_overrides,
)


def build_cli_exchange_context(consumption_file: str, original_filename: str | None = None) -> tuple[str | None, dict]:
    """Build FX context for CLI usage, aligned with API processing behavior."""
    from api.services.calculation_service import CalculationService

    svc = CalculationService()
    filename = original_filename or Path(consumption_file).name
    month_hint = svc._parse_month_from_filename(filename)
    has_rmb_rows = svc._contains_rmb_consumption(consumption_file, month_hint=month_hint)
    has_eur_rows = svc._contains_eur_consumption(consumption_file, month_hint=month_hint)
    has_jpy_rows = svc._contains_jpy_consumption(consumption_file, month_hint=month_hint)
    exchange_context = svc._build_daily_exchange_context(require_snapshot=has_rmb_rows or has_eur_rows or has_jpy_rows)
    return month_hint or None, exchange_context


# CLI entry point
if __name__ == '__main__':
    import sys

    script_dir = Path(__file__).parent
    consumption_file = script_dir / '璐﹀崟妯℃澘.xlsx'
    contract_file = script_dir / '鍚堝悓.xlsx'

    if len(sys.argv) >= 3:
        consumption_file = sys.argv[1]
        contract_file = sys.argv[2]

    use_feishu = "--feishu" in sys.argv
    feishu_conf = None

    if use_feishu:
        try:
            from fetch_feishu_contracts import APP_ID, APP_SECRET, APP_TOKEN
            feishu_conf = {
                'app_id': APP_ID, 'app_secret': APP_SECRET, 'app_token': APP_TOKEN
            }
            print("Enabled Feishu Mode.")
        except ImportError:
            print("鏃犳硶瀵煎叆 fetch_feishu_contracts 閰嶇疆")

    if not Path(consumption_file).exists():
        print(f"閿欒: 娑堣€楁暟鎹枃浠朵笉瀛樺湪: {consumption_file}")
        sys.exit(1)

    if not use_feishu and not Path(contract_file).exists():
        print(f"閿欒: 鍚堝悓鏉℃鏂囦欢涓嶅瓨鍦? {contract_file}")
        sys.exit(1)

    try:
        calculation_date, exchange_context = build_cli_exchange_context(
            str(consumption_file),
            Path(consumption_file).name,
        )
        output = calculate_service_fees(
            str(consumption_file),
            str(contract_file),
            feishu_config=feishu_conf,
            calculation_date=calculation_date,
            exchange_context=exchange_context,
        )
        print(f"\n瀹屾垚! 杈撳嚭鏂囦欢: {output}")
    except Exception as exc:
        print(f"閿欒: {exc}")
        sys.exit(1)

