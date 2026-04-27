# -*- coding: utf-8 -*-
import pandas as pd
import pytest
from openpyxl import load_workbook

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
            "eur_tt_buy": 9.00,
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

    result = pd.read_excel(out, sheet_name="_CALC_DATA")
    assert len(result) == 2
    # USD 1000 * 10% = 100
    # RMB 7000 * (1.10/7.20) = 1069.444... USD; fee ~= 106.94
    assert pytest.approx(result["服务费"].fillna(0).sum(), rel=1e-4) == 206.94


def test_rmb_summary_sheet_bill_total_fallback_converts_then_calculates(tmp_path, monkeypatch):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    rmb_df = pd.DataFrame(
        [
            {
                "月份归属": "2026-03-01",
                "媒介": "LinkedIn",
                "母公司": "测试客户A",
                "预付/后付": "预付",
                "服务类型": "代投",
                "代投/咨询拆分": 7200,
                "账单汇总": 7200,
            }
        ]
    )

    with pd.ExcelWriter(src) as writer:
        rmb_df.to_excel(writer, sheet_name="2026年人民币汇总", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "LinkedIn 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年3月",
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out, sheet_name="_CALC_DATA")
    assert pytest.approx(float(result["代投消耗"].fillna(0).iloc[0]), rel=1e-4) == 1100.0
    assert pytest.approx(float(result["汇总纯花费"].fillna(0).iloc[0]), rel=1e-4) == 1100.0
    assert pytest.approx(float(result["服务费"].fillna(0).iloc[0]), rel=1e-4) == 110.0


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


def test_summary_includes_dst_column_without_nbsp(tmp_path, monkeypatch):
    src = tmp_path / "2026年1月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    usd_df = pd.DataFrame(_base_rows())
    usd_df["代投消耗"] = 100
    usd_df["监管运营费用/数字服务税(DST)"] = 1.23

    with pd.ExcelWriter(src) as writer:
        usd_df.to_excel(writer, sheet_name="USD", index=False)

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
    # net(100) + service_fee(10) + dst(1.23) = 111.23
    assert pytest.approx(result["汇总"].iloc[0], rel=1e-4) == 111.23


def test_result_header_normalization_handles_variant_columns(tmp_path, monkeypatch):
    src = tmp_path / "2026年1月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    usd_df = pd.DataFrame(
        [
            {
                "母公司 ": "测试客户A",
                "媒介 ": "Google",
                "服务类型 ": "代投",
                "代投消耗 ": 0,
                "流水消耗 ": 0,
                "汇总纯消耗": 100,
                "coupon": 2,
                "监管运营费用/数字服务税 (DST)\xa0": 1.23,
            }
        ]
    )

    with pd.ExcelWriter(src) as writer:
        usd_df.to_excel(writer, sheet_name="USD", index=False)

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
    assert "汇总纯花费" in result.columns
    assert "汇总纯消耗" not in result.columns
    assert "Coupon" in result.columns
    assert "监管运营费用/数字服务税(DST)" in result.columns
    # net(100) + coupon(2) + dst(1.23) = 103.23
    assert pytest.approx(result["汇总"].iloc[0], rel=1e-4) == 103.23


def test_summary_includes_dst_when_header_is_short_alias(tmp_path, monkeypatch):
    src = tmp_path / "2026年1月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    usd_df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 100,
                "流水消耗": 0,
                "监管费": 2.5,
            }
        ]
    )

    with pd.ExcelWriter(src) as writer:
        usd_df.to_excel(writer, sheet_name="USD", index=False)

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
    # net(100) + service_fee(10) + dst(2.5) = 112.5
    assert pytest.approx(result["汇总"].iloc[0], rel=1e-4) == 112.5


def test_header_normalization_prefers_nonzero_variant_numeric_value(tmp_path, monkeypatch):
    src = tmp_path / "2026年1月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    usd_df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 100,
                "流水消耗": 0,
                "监管运营费用/数字服务税(DST)": 0,
                "监管费": 3.3,
            }
        ]
    )

    with pd.ExcelWriter(src) as writer:
        usd_df.to_excel(writer, sheet_name="USD", index=False)

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
    # net(100) + service_fee(10) + dst(3.3) = 113.3
    assert pytest.approx(result["汇总"].iloc[0], rel=1e-4) == 113.3


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


def test_eur_sheet_converts_with_hangseng_snapshot(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    eur_df = pd.DataFrame(_base_rows())
    eur_df["代投消耗"] = 800

    with pd.ExcelWriter(src) as writer:
        eur_df.to_excel(writer, sheet_name="EUR", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    assert pytest.approx(result["服务费"].fillna(0).sum(), rel=1e-4) == 100.0


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
                    "eur_tt_buy": 9.0,
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


def test_other_sheet_eur_alias_normalizes_to_eur(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    other_df = pd.DataFrame(_base_rows())
    other_df["代投消耗"] = 800
    other_df["币种"] = "欧元"

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
    assert result["币种"].iloc[0] == "EUR"
    assert pytest.approx(result["服务费"].fillna(0).sum(), rel=1e-4) == 100.0


def test_other_currency_summary_sheet_bill_total_fallback_converts_then_calculates(tmp_path, monkeypatch):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    other_df = pd.DataFrame(
        [
            {
                "月份归属": "2026-03-01",
                "媒介": "Google",
                "母公司": "测试客户A",
                "币种": "欧元",
                "预付/后付": "后付",
                "服务类型": "代投",
                "代投/咨询拆分": 800,
                "账单汇总": 800,
            }
        ]
    )

    with pd.ExcelWriter(src) as writer:
        other_df.to_excel(writer, sheet_name="2026年3月其他币种", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年3月",
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out, sheet_name="_CALC_DATA")
    assert result["币种"].iloc[0] == "EUR"
    assert pytest.approx(float(result["代投消耗"].fillna(0).iloc[0]), rel=1e-4) == 1000.0
    assert pytest.approx(float(result["服务费"].fillna(0).iloc[0]), rel=1e-4) == 100.0


def test_per_media_fixed_fee_is_applied_on_first_matching_row(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 100,
                "流水消耗": 0,
                "Coupon": 0,
            },
            {
                "母公司": "测试客户A",
                "媒介": "Facebook",
                "服务类型": "代投",
                "代投消耗": 300,
                "流水消耗": 0,
                "Coupon": 0,
            },
        ]
    )
    with pd.ExcelWriter(src) as writer:
        df.to_excel(writer, sheet_name="USD", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "各1000+消耗*7%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    fixed_map = result.set_index("媒介")["固定服务费"].fillna(0).astype(float).to_dict()
    assert pytest.approx(fixed_map["Google"], rel=1e-4) == 1000.0
    assert pytest.approx(fixed_map["Facebook"], rel=1e-4) == 1000.0
    assert pytest.approx(result["固定服务费"].fillna(0).sum(), rel=1e-4) == 2000.0


def test_per_media_fixed_fee_not_collapsed_by_aggregate_waiver_phrase(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    df = pd.DataFrame(
        [
            {
                "母公司": "Acmer",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 100,
                "流水消耗": 0,
                "Coupon": 0,
            },
            {
                "母公司": "Acmer",
                "媒介": "Facebook",
                "服务类型": "代投",
                "代投消耗": 300,
                "流水消耗": 0,
                "Coupon": 0,
            },
        ]
    )
    with pd.ExcelWriter(src) as writer:
        df.to_excel(writer, sheet_name="USD", index=False)

    monkeypatch.setattr(
        "billing.fee_engine.load_contract_terms",
        lambda _p: {
            "Acmer": "FB/GG 各1000+消耗*7%，如合计消耗*7%大于等于3000，则免收固定的2000。GG流水服务费2%。"
        },
    )

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    fixed_map = result.set_index("媒介")["固定服务费"].fillna(0).astype(float).to_dict()
    assert pytest.approx(fixed_map["Google"], rel=1e-4) == 1000.0
    assert pytest.approx(fixed_map["Facebook"], rel=1e-4) == 1000.0
    assert pytest.approx(result["固定服务费"].fillna(0).sum(), rel=1e-4) == 2000.0


def test_fixed_fee_not_charged_when_customer_has_no_managed_consumption(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 0,
                "流水消耗": 0,
                "Coupon": 0,
            },
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "流水",
                "代投消耗": 0,
                "流水消耗": 500,
                "Coupon": 0,
            },
        ]
    )
    with pd.ExcelWriter(src) as writer:
        df.to_excel(writer, sheet_name="USD", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "各1000+消耗*7%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    assert pytest.approx(result["固定服务费"].fillna(0).sum(), rel=1e-4) == 0.0


def test_customer_level_fixed_fee_is_applied_once(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 1,
                "流水消耗": 0,
                "Coupon": 0,
            },
            {
                "母公司": "测试客户A",
                "媒介": "Facebook",
                "服务类型": "代投",
                "代投消耗": 1,
                "流水消耗": 0,
                "Coupon": 0,
            },
            {
                "母公司": "测试客户A",
                "媒介": "TikTok",
                "服务类型": "代投",
                "代投消耗": 1,
                "流水消耗": 0,
                "Coupon": 0,
            },
        ]
    )
    with pd.ExcelWriter(src) as writer:
        df.to_excel(writer, sheet_name="USD", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "合计基础1000+消耗*7%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out)
    fixed_values = [float(v or 0) for v in result["固定服务费"].fillna(0).tolist()]
    assert fixed_values == [1000.0, 0.0, 0.0]
    assert pytest.approx(sum(fixed_values), rel=1e-4) == 1000.0


def test_result_workbook_preserves_source_sheets_and_hidden_calc_data(tmp_path, monkeypatch):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    usd_df = pd.DataFrame(_base_rows())
    rmb_df = pd.DataFrame(_base_rows())
    rmb_df["代投消耗"] = 7200

    with pd.ExcelWriter(src) as writer:
        usd_df.to_excel(writer, sheet_name="2026年3月美金", index=False)
        rmb_df.to_excel(writer, sheet_name="2026年人民币汇总", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年3月",
        exchange_context=_exchange_context(),
    )

    workbook = pd.ExcelFile(out)
    assert workbook.sheet_names == ["2026年3月美金", "2026年人民币汇总", "_CALC_DATA"]

    hidden_df = pd.read_excel(out, sheet_name="_CALC_DATA")
    assert hidden_df["来源Sheet"].tolist() == ["2026年3月美金", "2026年人民币汇总"]
    assert hidden_df["币种"].tolist() == ["USD", "RMB"]
    assert pytest.approx(hidden_df["服务费"].fillna(0).sum(), rel=1e-4) == 210.0

    book = load_workbook(out)
    assert book["_CALC_DATA"].sheet_state == "hidden"
    book.close()


def test_usd_visible_sheet_hides_fx_audit_columns(tmp_path, monkeypatch):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    usd_df = pd.DataFrame(_base_rows())

    with pd.ExcelWriter(src) as writer:
        usd_df.to_excel(writer, sheet_name="2026年3月美金", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年3月",
        exchange_context=_exchange_context(),
    )

    visible_df = pd.read_excel(out, sheet_name="2026年3月美金")
    hidden_df = pd.read_excel(out, sheet_name="_CALC_DATA")
    assert "换汇汇率" not in visible_df.columns
    assert "换汇后代投消耗USD" not in visible_df.columns
    assert "换汇汇率" in hidden_df.columns


def test_client_account_sheet_writes_month_columns_next_to_target_consumption(tmp_path, monkeypatch):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    client_account_df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "币种": "RMB",
                "2026年2月消耗": 999999,
                "2026年3月消耗": 7200,
            }
        ]
    )

    with pd.ExcelWriter(src) as writer:
        client_account_df.to_excel(writer, sheet_name="客户端口代投2022.9-2026.3", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年3月",
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out, sheet_name="客户端口代投2022.9-2026.3")
    target_index = result.columns.get_loc("2026年3月消耗")
    assert list(result.columns[target_index + 1 : target_index + 5]) == [
        "2026年3月服务费",
        "2026年3月固定服务费",
        "2026年3月换汇汇率",
        "2026年3月换汇后消耗USD",
    ]
    assert pytest.approx(float(result["2026年3月服务费"].fillna(0).iloc[0]), rel=1e-4) == 110.0
    assert pytest.approx(float(result["2026年3月固定服务费"].fillna(0).iloc[0]), rel=1e-4) == 0.0
    assert pytest.approx(float(result["2026年3月换汇汇率"].fillna(0).iloc[0]), rel=1e-6) == 1.1 / 7.2
    assert pytest.approx(float(result["2026年3月换汇后消耗USD"].fillna(0).iloc[0]), rel=1e-4) == 1100.0


def test_client_account_sheet_blank_currency_defaults_to_usd(tmp_path, monkeypatch):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    out = tmp_path / "out.xlsx"

    client_account_df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "渠道": "客户端口账户",
                "币种": "",
                "2026年3月消耗": 1000,
            }
        ]
    )

    with pd.ExcelWriter(src) as writer:
        client_account_df.to_excel(writer, sheet_name="客户端口账户代投2022.9-2026.3", index=False)

    monkeypatch.setattr("billing.fee_engine.load_contract_terms", lambda _p: {"测试客户A": "Google 10%"})

    calculate_service_fees(
        str(src),
        contract_path="dummy.xlsx",
        output_path=str(out),
        use_db=False,
        calculation_date="2026年3月",
        exchange_context=_exchange_context(),
    )

    result = pd.read_excel(out, sheet_name="客户端口账户代投2022.9-2026.3")
    assert pytest.approx(float(result["2026年3月服务费"].fillna(0).iloc[0]), rel=1e-4) == 100.0
    assert "2026年3月换汇汇率" not in result.columns
    assert "2026年3月换汇后消耗USD" not in result.columns


def test_service_type_variant_liushui_plus_daitou_is_normalized(tmp_path, monkeypatch):
    src = tmp_path / "consumption.xlsx"
    out = tmp_path / "out.xlsx"

    df = pd.DataFrame(
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "流水+代投",
                "代投消耗": 100,
                "流水消耗": 50,
                "Coupon": 0,
            },
        ]
    )
    with pd.ExcelWriter(src) as writer:
        df.to_excel(writer, sheet_name="USD", index=False)

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
    # 代投100*10% + 流水50*10% = 15
    assert pytest.approx(float(result["服务费"].fillna(0).iloc[0]), rel=1e-4) == 15.0
