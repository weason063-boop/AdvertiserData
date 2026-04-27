# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

from api.services.calculation_service import CalculationService


def _write_sheet(path: Path, sheet: str, rows: list[dict]):
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False)


def _write_workbook(path: Path, sheets: dict[str, list[dict]]):
    with pd.ExcelWriter(path) as writer:
        for sheet_name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)


def test_process_without_foreign_currency_allows_empty_snapshot(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "2026年1月消耗明细.xlsx"
    _write_sheet(
        src,
        "USD",
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 1000,
                "流水消耗": 0,
            }
        ],
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc, "_update_stats_from_result", lambda *_args, **_kwargs: None)

    monkeypatch.setattr(svc._daily_fx_snapshot_service, "get_today_snapshot", lambda: None)

    def fake_calculate_service_fees(*_args, **_kwargs):
        assert _kwargs["exchange_context"]["hangseng_today"] == {}
        out_path = tmp_path / "result.xlsx"
        pd.DataFrame(
            [{"母公司": "测试客户A", "代投消耗": 1000, "流水消耗": 0, "服务费": 100, "固定服务费": 0}]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    result = svc.process_local_file(str(src), src.name)
    assert result["status"] == "ok"


def test_process_with_jpy_missing_daily_snapshot_returns_clear_error(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "2026年1月消耗明细.xlsx"
    _write_sheet(
        src,
        "JPY",
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 100000,
                "流水消耗": 0,
            }
        ],
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc._daily_fx_snapshot_service, "get_today_snapshot", lambda: None)

    with pytest.raises(HTTPException) as exc:
        svc.process_local_file(str(src), src.name)

    assert exc.value.status_code == 400
    assert "快照" in str(exc.value.detail)


def test_process_with_rmb_uses_daily_snapshot(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "2026年1月消耗明细.xlsx"
    _write_sheet(
        src,
        "RMB",
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 7000,
                "流水消耗": 0,
            }
        ],
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc, "_update_stats_from_result", lambda *_args, **_kwargs: None)

    snapshot = {
        "rate_date": "2026-03-16",
        "cny_tt_buy": 1.1,
        "eur_tt_buy": 9.0,
        "usd_tt_sell": 7.2,
        "jpy_tt_sell": 0.05,
        "usd_tt_buy": 7.1,
        "source": "hangseng_daily_snapshot",
        "pub_time": "2026-03-16 09:30:00",
    }
    monkeypatch.setattr(svc._daily_fx_snapshot_service, "get_today_snapshot", lambda: snapshot)

    def fake_calculate_service_fees(*_args, **_kwargs):
        assert _kwargs["exchange_context"]["hangseng_today"]["rate_date"] == "2026-03-16"
        out_path = tmp_path / "result.xlsx"
        pd.DataFrame(
            [{"母公司": "测试客户A", "代投消耗": 1000, "流水消耗": 0, "服务费": 100, "固定服务费": 0}]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    result = svc.process_local_file(str(src), src.name)
    assert result["status"] == "ok"


def test_process_with_eur_missing_daily_snapshot_returns_clear_error(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "2026年1月消耗明细.xlsx"
    _write_sheet(
        src,
        "EUR",
        [
            {
                "母公司": "测试客户A",
                "媒介": "Google",
                "服务类型": "代投",
                "代投消耗": 800,
                "流水消耗": 0,
            }
        ],
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc._daily_fx_snapshot_service, "get_today_snapshot", lambda: None)

    with pytest.raises(HTTPException) as exc:
        svc.process_local_file(str(src), src.name)

    assert exc.value.status_code == 400
    assert "快照" in str(exc.value.detail)


def test_process_with_client_account_rmb_target_month_requires_daily_snapshot(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "2026年3月消耗明细.xlsx"
    _write_workbook(
        src,
        {
            "客户端口代投2022.9-2026.3": [
                {
                    "母公司": "测试客户A",
                    "媒介": "Google",
                    "币种": "RMB",
                    "2026年2月消耗": 0,
                    "2026年3月消耗": 7200,
                }
            ]
        },
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc._daily_fx_snapshot_service, "get_today_snapshot", lambda: None)

    with pytest.raises(HTTPException) as exc:
        svc.process_local_file(str(src), src.name)

    assert exc.value.status_code == 400
    assert "快照" in str(exc.value.detail)


def test_validate_client_account_sheet_requires_currency_column(tmp_path):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    _write_workbook(
        src,
        {
            "客户端口代投2022.9-2026.3": [
                {
                    "母公司": "测试客户A",
                    "媒介": "Google",
                    "2026年3月消耗": 7200,
                }
            ]
        },
    )

    svc = CalculationService()
    with pytest.raises(HTTPException) as exc:
        svc._validate_consumption_workbook(str(src), src.name)

    assert exc.value.status_code == 400
    assert "币种" in str(exc.value.detail)


def test_validate_client_account_sheet_requires_matching_target_month_column(tmp_path):
    src = tmp_path / "2026年3月消耗明细.xlsx"
    _write_workbook(
        src,
        {
            "客户端口代投2022.9-2026.3": [
                {
                    "母公司": "测试客户A",
                    "媒介": "Google",
                    "币种": "USD",
                    "2026年2月消耗": 1000,
                }
            ]
        },
    )

    svc = CalculationService()
    with pytest.raises(HTTPException) as exc:
        svc._validate_consumption_workbook(str(src), src.name)

    assert exc.value.status_code == 400
    assert "客户端口账户代投" in str(exc.value.detail)
    assert "2026-03" in str(exc.value.detail)


def test_process_with_client_account_blank_currency_defaults_to_usd(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "2026年3月消耗明细.xlsx"
    _write_workbook(
        src,
        {
            "客户端口账户代投2022.9-2026.3": [
                {
                    "母公司": "测试客户A",
                    "媒介": "Google",
                    "渠道": "客户端口账户",
                    "币种": "",
                    "2026年3月消耗": 1000,
                }
            ]
        },
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc, "_update_stats_from_result", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(svc._daily_fx_snapshot_service, "get_today_snapshot", lambda: None)

    def fake_calculate_service_fees(*_args, **_kwargs):
        assert _kwargs["exchange_context"]["hangseng_today"] == {}
        out_path = tmp_path / "result.xlsx"
        pd.DataFrame(
            [{"母公司": "测试客户A", "代投消耗": 1000, "流水消耗": 0, "服务费": 100, "固定服务费": 0}]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    result = svc.process_local_file(str(src), src.name)
    assert result["status"] == "ok"
