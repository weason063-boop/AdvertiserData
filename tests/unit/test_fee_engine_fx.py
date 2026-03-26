# -*- coding: utf-8 -*-
import pandas as pd
import pytest

from billing.fee_engine import calculate_service_fees


def _base_rows():
    return [
        {
            "母公司": "测试客户A",
            "媒介": "Google",
            "服务类型": "代投",
            "代投消耗": 1000,
            "流水消耗": 0,
            "Coupon": 0,
        }
    ]


def _exchange_context():
    return {
        "hangseng_today": {
            "cny_tt_buy": 1.10,
            "usd_tt_sell": 7.20,
            "jpy_tt_sell": 0.05,
            "usd_tt_buy": 7.10,
            "rate_date": "2026-03-15",
            "source": "hangseng_daily_snapshot",
        }
    }


def test_rmb_sheet_converts_then_calculates(tmp_path, monkeypatch):
    src = tmp_path / "2026年1月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    usd_df = pd.DataFrame(_base_rows())
    rmb_df = pd.DataFrame(_base_rows())
    rmb_df["代投消耗"] = 7000

    with pd.ExcelWriter(src) as writer:
        usd_df.to_excel(writer, sheet_name="USD", index=False)
        rmb_df.to_excel(writer, sheet_name="RMB", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年1月",
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    assert len(result) == 2
    # USD 1000 * 10% = 100
    # RMB 7000 * (1.10/7.20) = 1069.444... USD; fee ~= 106.94
    assert pytest.approx(result["服务费"].fillna(0).sum(), rel=1e-4) == 206.94


def test_summary_follows_converted_spend_invariant(tmp_path, monkeypatch):
    src = tmp_path / "2026年1月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    rmb_df = pd.DataFrame(_base_rows())
    rmb_df["代投消耗"] = 7000
    rmb_df["汇总纯花费"] = 7000

    with pd.ExcelWriter(src) as writer:
        rmb_df.to_excel(writer, sheet_name="RMB", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年1月",
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    # Converted spend ~= 1069.44; fee ~= 106.94; total ~= 1176.38
    assert pytest.approx(result["汇总"].iloc[0], rel=1e-4) == 1176.38


def test_jpy_sheet_converts_with_hangseng_snapshot(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    jpy_df = pd.DataFrame(_base_rows())
    jpy_df["代投消耗"] = 100000

    with pd.ExcelWriter(src) as writer:
        jpy_df.to_excel(writer, sheet_name="JPY", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    assert pytest.approx(result["服务费"].fillna(0).sum(), rel=1e-4) == 70.42


def test_jpy_missing_snapshot_fields_raises(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"

    jpy_df = pd.DataFrame(_base_rows())
    jpy_df["代投消耗"] = 100000

    with pd.ExcelWriter(src) as writer:
        jpy_df.to_excel(writer, sheet_name="JPY", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    with pytest.raises(ValueError, match="JPY"):
        calculate_service_fees(
            str(src),
            contract_path="dummy.xlsx",
            use_db=False,
            exchange_context={
                "hangseng_today": {
                    "cny_tt_buy": 1.1,
                    "usd_tt_sell": 7.2,
                    "usd_tt_buy": 7.1,
                }
            },
        )


def test_other_sheet_jpy_alias_normalizes_to_jpy(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    other_df = pd.DataFrame(_base_rows())
    other_df["代投消耗"] = 100000
    other_df["币种"] = "日元"

    with pd.ExcelWriter(src) as writer:
        other_df.to_excel(writer, sheet_name="其他币种", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    assert result["币种"].iloc[0] == "JPY"
    assert pytest.approx(result["服务费"].fillna(0).sum(), rel=1e-4) == 70.42
