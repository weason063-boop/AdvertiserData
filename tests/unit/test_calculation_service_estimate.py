# -*- coding: utf-8 -*-
import shutil
import uuid
from pathlib import Path

import pandas as pd
import pytest

from api.services.calculation_service import CalculationService


COL_PARENT = "\u6bcd\u516c\u53f8"
COL_MEDIA = "\u5a92\u4ecb"
COL_DELIVERY_TYPE = "\u6295\u653e\u7c7b\u578b"
COL_SERVICE_TYPE = "\u670d\u52a1\u7c7b\u578b"
COL_MANAGED_CONSUMPTION = "\u4ee3\u6295\u6d88\u8017"
COL_FLOW_CONSUMPTION = "\u6d41\u6c34\u6d88\u8017"
COL_SERVICE_FEE = "\u670d\u52a1\u8d39"
COL_FIXED_SERVICE_FEE = "\u56fa\u5b9a\u670d\u52a1\u8d39"
COL_EST_SERVICE_FEE = "\u9884\u4f30\u670d\u52a1\u8d39"
COL_EST_FIXED_SERVICE_FEE = "\u9884\u4f30\u56fa\u5b9a\u670d\u52a1\u8d39"
SERVICE_MANAGED = "\u4ee3\u6295"
SERVICE_FLOW = "\u6d41\u6c34"


def _write_estimate_sheet(path: Path, rows: list[dict], *, sheet_name: str = "Sheet1") -> None:
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)


@pytest.fixture
def workspace_tmp_path():
    root = Path(__file__).resolve().parents[1] / ".tmp"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"estimate_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_prepare_estimate_input_detects_dynamic_columns_and_aggregates(workspace_tmp_path, monkeypatch):
    consumption_col = "\u8d5b\u6587\u601dQ1\u6d88\u8017\u9884\u4f30\uff0803.01-03.31\uff09"
    gross_profit_col = "\u8d5b\u6587\u601d\u8d22\u5e7426.3\u6708\u6bdb\u5229\u9884\u4f30"
    src = workspace_tmp_path / "estimate_template.xlsx"
    _write_estimate_sheet(
        src,
        [
            {
                COL_MEDIA: "Google",
                COL_DELIVERY_TYPE: SERVICE_MANAGED,
                COL_PARENT: "Acme",
                consumption_col: 100,
                gross_profit_col: 30,
            },
            {
                COL_MEDIA: "Google",
                COL_DELIVERY_TYPE: SERVICE_MANAGED,
                COL_PARENT: "Acme",
                consumption_col: 150,
                gross_profit_col: 20,
            },
            {
                COL_MEDIA: "Meta",
                COL_DELIVERY_TYPE: SERVICE_FLOW,
                COL_PARENT: "Beta",
                consumption_col: 80,
                gross_profit_col: 10,
            },
        ],
    )

    svc = CalculationService()
    monkeypatch.setattr(
        "billing.contract_loader.load_contract_terms_from_db",
        lambda: {"Acme": "tier", "Beta": "tier"},
    )

    (
        _,
        sheet2_seed_df,
        calc_input_df,
        got_consumption_col,
        got_gross_profit_col,
        got_sheet_name,
    ) = svc._prepare_estimate_calculation_input(str(src))

    assert got_consumption_col == consumption_col
    assert got_gross_profit_col == gross_profit_col
    assert got_sheet_name == "Sheet1"

    acme_row = sheet2_seed_df[
        (sheet2_seed_df[COL_PARENT] == "Acme")
        & (sheet2_seed_df[COL_SERVICE_TYPE] == SERVICE_MANAGED)
        & (sheet2_seed_df[COL_MEDIA] == "Google")
    ].iloc[0]
    assert acme_row["_estimate_consumption"] == 250
    assert acme_row["_estimate_gross_profit"] == 50

    managed_input = calc_input_df[
        (calc_input_df[COL_PARENT] == "Acme")
        & (calc_input_df[COL_SERVICE_TYPE] == SERVICE_MANAGED)
        & (calc_input_df[COL_MEDIA] == "Google")
    ].iloc[0]
    assert managed_input[COL_MANAGED_CONSUMPTION] == 250
    assert managed_input[COL_FLOW_CONSUMPTION] == 0

    flow_input = calc_input_df[
        (calc_input_df[COL_PARENT] == "Beta")
        & (calc_input_df[COL_SERVICE_TYPE] == SERVICE_FLOW)
        & (calc_input_df[COL_MEDIA] == "Meta")
    ].iloc[0]
    assert flow_input[COL_MANAGED_CONSUMPTION] == 0
    assert flow_input[COL_FLOW_CONSUMPTION] == 80


def test_prepare_estimate_input_matches_contract_case_insensitive(workspace_tmp_path, monkeypatch):
    consumption_col = "\u8d5b\u6587\u601dQ1\u6d88\u8017\u9884\u4f30\uff0803.01-03.31\uff09"
    gross_profit_col = "\u8d5b\u6587\u601d\u8d22\u5e7426.3\u6708\u6bdb\u5229\u9884\u4f30"
    src = workspace_tmp_path / "estimate_template.xlsx"
    _write_estimate_sheet(
        src,
        [
            {
                COL_MEDIA: "Google",
                COL_DELIVERY_TYPE: SERVICE_MANAGED,
                COL_PARENT: "blackseries",
                consumption_col: 120,
                gross_profit_col: 12,
            },
        ],
    )

    svc = CalculationService()
    monkeypatch.setattr(
        "billing.contract_loader.load_contract_terms_from_db",
        lambda: {"BlackSeries": "tier"},
    )

    _, sheet2_seed_df, calc_input_df, _, _, got_sheet_name = svc._prepare_estimate_calculation_input(str(src))

    assert sheet2_seed_df.iloc[0]["_contract_client"] == "BlackSeries"
    assert calc_input_df.iloc[0][COL_PARENT] == "BlackSeries"
    assert got_sheet_name == "Sheet1"


def test_prepare_estimate_input_supports_non_sheet1(workspace_tmp_path, monkeypatch):
    consumption_col = "\u9884\u4f30\u6d88\u8017\u5217"
    gross_profit_col = "\u9884\u4f30\u6bdb\u5229\u5217"
    src = workspace_tmp_path / "estimate_template_custom_sheet.xlsx"
    _write_estimate_sheet(
        src,
        [
            {
                COL_MEDIA: "Google",
                COL_DELIVERY_TYPE: SERVICE_MANAGED,
                COL_PARENT: "Acme",
                consumption_col: 200,
                gross_profit_col: 40,
            },
        ],
        sheet_name="\u9884\u4f30\u660e\u7ec6",
    )

    svc = CalculationService()
    monkeypatch.setattr(
        "billing.contract_loader.load_contract_terms_from_db",
        lambda: {"Acme": "tier"},
    )

    _, sheet2_seed_df, calc_input_df, _, _, got_sheet_name = svc._prepare_estimate_calculation_input(str(src))

    assert got_sheet_name == "\u9884\u4f30\u660e\u7ec6"
    assert sheet2_seed_df.iloc[0][COL_PARENT] == "Acme"
    assert calc_input_df.iloc[0][COL_MANAGED_CONSUMPTION] == 200


def test_process_estimate_local_file_disables_stats_persistence(workspace_tmp_path, monkeypatch):
    consumption_col = "\u8d5b\u6587\u601dQ1\u6d88\u8017\u9884\u4f30\uff0803.01-03.31\uff09"
    gross_profit_col = "\u8d5b\u6587\u601d\u8d22\u5e7426.3\u6708\u6bdb\u5229\u9884\u4f30"
    uploads_dir = workspace_tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = workspace_tmp_path / "2026-03-estimate.xlsx"
    _write_estimate_sheet(
        src,
        [
            {
                COL_MEDIA: "Google",
                COL_DELIVERY_TYPE: SERVICE_MANAGED,
                COL_PARENT: "blackseries",
                consumption_col: 120,
                gross_profit_col: 12,
            },
        ],
        sheet_name="\u9884\u4f30\u660e\u7ec6",
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(
        "billing.contract_loader.load_contract_terms_from_db",
        lambda: {"BlackSeries": "tier"},
    )
    monkeypatch.setattr(svc, "_register_result", lambda **_kwargs: {"id": "a" * 32})
    monkeypatch.setattr(svc, "_audit", lambda **_kwargs: None)

    captured: dict[str, object] = {}

    def fake_run_calculation_core(
        file_path: str,
        original_filename: str,
        *,
        persist_stats: bool,
        require_fx_snapshot: bool,
        exchange_context=None,
        output_path: str | None = None,
    ) -> str:
        captured["file_path"] = file_path
        captured["original_filename"] = original_filename
        captured["persist_stats"] = persist_stats
        captured["require_fx_snapshot"] = require_fx_snapshot
        captured["exchange_context"] = exchange_context
        captured["output_path"] = output_path

        assert output_path
        pd.DataFrame(
            [
                {
                    COL_PARENT: "BlackSeries",
                    COL_SERVICE_TYPE: SERVICE_MANAGED,
                    COL_MEDIA: "Google",
                    COL_SERVICE_FEE: 8.88,
                    COL_FIXED_SERVICE_FEE: 1.23,
                }
            ]
        ).to_excel(output_path, index=False)
        return output_path

    monkeypatch.setattr(svc, "_run_calculation_core", fake_run_calculation_core)

    result = svc.process_estimate_local_file(
        str(src),
        src.name,
        owner_username="tester",
        operation="estimate_calculate",
    )

    assert result["status"] == "ok"
    assert captured["persist_stats"] is False
    assert captured["require_fx_snapshot"] is False
    assert captured["exchange_context"] == {"hangseng_today": {}}
    assert result["output_file"].endswith("_estimate_results.xlsx")

    output_file = uploads_dir / result["output_file"]
    assert output_file.exists()

    output_sheet1 = pd.read_excel(output_file, sheet_name="\u9884\u4f30\u660e\u7ec6")
    assert output_sheet1.columns.tolist()[0] == COL_MEDIA

    output_sheet2 = pd.read_excel(output_file, sheet_name="Sheet2")
    assert output_sheet2.columns.tolist() == [
        COL_PARENT,
        COL_SERVICE_TYPE,
        COL_MEDIA,
        consumption_col,
        COL_EST_SERVICE_FEE,
        COL_EST_FIXED_SERVICE_FEE,
        gross_profit_col,
    ]
    assert float(output_sheet2.iloc[0][COL_EST_SERVICE_FEE]) == 8.88
    assert float(output_sheet2.iloc[0][COL_EST_FIXED_SERVICE_FEE]) == 1.23


def test_process_estimate_local_file_sheet2_keeps_fixed_fee_ratio_allocation(workspace_tmp_path, monkeypatch):
    consumption_col = "赛文思Q2消耗预估（04.01-04.30）"
    gross_profit_col = "赛文思财年26.4月毛利预估"
    uploads_dir = workspace_tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = workspace_tmp_path / "2026-04-estimate.xlsx"
    _write_estimate_sheet(
        src,
        [
            {
                COL_MEDIA: "Google",
                COL_DELIVERY_TYPE: SERVICE_MANAGED,
                COL_PARENT: "blackseries",
                consumption_col: 100,
                gross_profit_col: 15,
            },
            {
                COL_MEDIA: "Facebook",
                COL_DELIVERY_TYPE: SERVICE_MANAGED,
                COL_PARENT: "blackseries",
                consumption_col: 300,
                gross_profit_col: 35,
            },
        ],
        sheet_name="预估明细",
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(
        "billing.contract_loader.load_contract_terms_from_db",
        lambda: {"BlackSeries": "tier"},
    )
    monkeypatch.setattr(svc, "_register_result", lambda **_kwargs: {"id": "b" * 32})
    monkeypatch.setattr(svc, "_audit", lambda **_kwargs: None)

    def fake_run_calculation_core(
        file_path: str,
        original_filename: str,
        *,
        persist_stats: bool,
        require_fx_snapshot: bool,
        exchange_context=None,
        output_path: str | None = None,
    ) -> str:
        assert output_path
        pd.DataFrame(
            [
                {
                    COL_PARENT: "BlackSeries",
                    COL_SERVICE_TYPE: SERVICE_MANAGED,
                    COL_MEDIA: "Google",
                    COL_SERVICE_FEE: 7.0,
                    COL_FIXED_SERVICE_FEE: 500.0,
                },
                {
                    COL_PARENT: "BlackSeries",
                    COL_SERVICE_TYPE: SERVICE_MANAGED,
                    COL_MEDIA: "Facebook",
                    COL_SERVICE_FEE: 21.0,
                    COL_FIXED_SERVICE_FEE: 1500.0,
                },
            ]
        ).to_excel(output_path, index=False)
        return output_path

    monkeypatch.setattr(svc, "_run_calculation_core", fake_run_calculation_core)

    result = svc.process_estimate_local_file(
        str(src),
        src.name,
        owner_username="tester",
        operation="estimate_calculate",
    )
    assert result["status"] == "ok"

    output_file = uploads_dir / result["output_file"]
    output_sheet2 = pd.read_excel(output_file, sheet_name="Sheet2")

    managed_rows = output_sheet2[
        (output_sheet2[COL_PARENT] == "BlackSeries")
        & (output_sheet2[COL_SERVICE_TYPE] == SERVICE_MANAGED)
    ].copy()
    managed_rows = managed_rows.set_index(COL_MEDIA)

    assert float(managed_rows.loc["Google", consumption_col]) == 100
    assert float(managed_rows.loc["Facebook", consumption_col]) == 300
    assert float(managed_rows.loc["Google", COL_EST_FIXED_SERVICE_FEE]) == 500.0
    assert float(managed_rows.loc["Facebook", COL_EST_FIXED_SERVICE_FEE]) == 1500.0
    assert float(managed_rows[COL_EST_FIXED_SERVICE_FEE].sum()) == 2000.0
