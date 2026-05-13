# -*- coding: utf-8 -*-
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

from api.services.calculation_service import CalculationService
from api.services.daily_fx_snapshot_service import DailyFxSnapshotService


def _write_sheet(path: Path, sheet: str, rows: list[dict]):
    with pd.ExcelWriter(path) as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name=sheet, index=False)


def _write_workbook(path: Path, sheets: dict[str, list[dict]]):
    with pd.ExcelWriter(path) as writer:
        for sheet_name, rows in sheets.items():
            pd.DataFrame(rows).to_excel(writer, sheet_name=sheet_name, index=False)


def _service_with_isolated_fx_state(uploads_dir: Path) -> CalculationService:
    return CalculationService(DailyFxSnapshotService(state_path=uploads_dir / "fx_state.json"))


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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc._daily_fx_snapshot_service, "get_today_snapshot", lambda: None)

    with pytest.raises(HTTPException) as exc:
        svc.process_local_file(str(src), src.name)

    assert exc.value.status_code == 400
    assert "快照" in str(exc.value.detail)


def test_process_with_rmb_uses_month_snapshot(tmp_path, monkeypatch):
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc, "_update_stats_from_result", lambda *_args, **_kwargs: None)

    svc._daily_fx_snapshot_service.upsert_snapshot(
        rate_date="2026-01-05",
        cny_tt_buy=1.1,
        eur_tt_buy=9.0,
        usd_tt_sell=7.2,
        jpy_tt_sell=0.05,
        usd_tt_buy=7.1,
        actor="tester",
    )

    def fake_calculate_service_fees(*_args, **_kwargs):
        assert _kwargs["exchange_context"]["hangseng_today"]["rate_date"] == "2026-01-05"
        out_path = tmp_path / "result.xlsx"
        pd.DataFrame(
            [{"母公司": "测试客户A", "代投消耗": 1000, "流水消耗": 0, "服务费": 100, "固定服务费": 0}]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    result = svc.process_local_file(str(src), src.name)
    assert result["status"] == "ok"


def test_prepare_fx_rate_choice_returns_multiple_month_candidates(tmp_path, monkeypatch):
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    svc._daily_fx_snapshot_service.upsert_snapshot(
        rate_date="2026-01-05",
        cny_tt_buy=1.1,
        eur_tt_buy=9.0,
        usd_tt_sell=7.2,
        jpy_tt_sell=0.05,
        usd_tt_buy=7.1,
        actor="tester",
    )
    svc._daily_fx_snapshot_service.upsert_snapshot(
        rate_date="2026-01-06",
        cny_tt_buy=1.2,
        eur_tt_buy=9.1,
        usd_tt_sell=7.3,
        jpy_tt_sell=0.051,
        usd_tt_buy=7.2,
        actor="tester",
    )

    choice = svc.prepare_fx_rate_choice(str(src), src.name)

    assert choice["status"] == "requires_fx_choice"
    assert choice["requires_fx_choice"] is True
    assert choice["fx_choice"]["month"] == "2026-01"
    assert choice["fx_choice"]["required_currencies"] == ["RMB"]
    assert [item["rate_date"] for item in choice["fx_choice"]["candidates"]] == [
        "2026-01-06",
        "2026-01-05",
    ]


def test_process_with_selected_fx_rate_date_locks_selected_snapshot(tmp_path, monkeypatch):
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc, "_update_stats_from_result", lambda *_args, **_kwargs: None)
    for rate_date, cny_tt_buy in [("2026-01-05", 1.1), ("2026-01-06", 1.2)]:
        svc._daily_fx_snapshot_service.upsert_snapshot(
            rate_date=rate_date,
            cny_tt_buy=cny_tt_buy,
            eur_tt_buy=9.0,
            usd_tt_sell=7.2,
            jpy_tt_sell=0.05,
            usd_tt_buy=7.1,
            actor="tester",
        )

    def fake_calculate_service_fees(*_args, **_kwargs):
        context = _kwargs["exchange_context"]
        assert context["hangseng_today"]["rate_date"] == "2026-01-05"
        assert context["fx_lock"]["selection"] == "user_selected"
        out_path = tmp_path / "selected_result.xlsx"
        pd.DataFrame(
            [{"母公司": "测试客户A", "代投消耗": 1000, "流水消耗": 0, "服务费": 100, "固定服务费": 0}]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    result = svc.process_local_file(str(src), src.name, selected_fx_rate_date="2026-01-05")

    assert result["status"] == "ok"
    assert result["fx_lock"]["status"] == "created"
    assert result["fx_lock"]["rate_date"] == "2026-01-05"
    assert result["fx_lock"]["selection"] == "user_selected"
    assert svc._daily_fx_snapshot_service.get_month_lock("2026-01")["rate_date"] == "2026-01-05"


def test_process_with_rmb_reuses_locked_month_snapshot(tmp_path, monkeypatch):
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(svc, "_update_stats_from_result", lambda *_args, **_kwargs: None)

    locked_snapshot = {
        "rate_date": "2026-01-05",
        "cny_tt_buy": 1.1,
        "eur_tt_buy": 9.0,
        "usd_tt_sell": 7.2,
        "jpy_tt_sell": 0.05,
        "usd_tt_buy": 7.1,
        "source": "manual",
        "pub_time": "2026-01-05 09:30:00",
    }
    svc._daily_fx_snapshot_service.lock_month_snapshot("2026-01", locked_snapshot, actor="tester")
    monkeypatch.setattr(
        svc._daily_fx_snapshot_service,
        "get_today_snapshot",
        lambda: {**locked_snapshot, "rate_date": "2026-05-12", "cny_tt_buy": 1.5},
    )

    def fake_calculate_service_fees(*_args, **_kwargs):
        context = _kwargs["exchange_context"]
        assert context["hangseng_today"]["rate_date"] == "2026-01-05"
        assert context["fx_lock"]["status"] == "reused"
        out_path = uploads_dir / "calc_results.xlsx"
        pd.DataFrame(
            [{"母公司": "测试客户A", "代投消耗": 1000, "流水消耗": 0, "服务费": 100, "固定服务费": 0}]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    result = svc.process_local_file(str(src), src.name)
    latest = svc.get_latest_result_info_for_user("system", operations={"calculate"})

    assert result["fx_lock"]["status"] == "reused"
    assert latest["calculation_month"] == "2026-01"
    assert latest["fx_snapshot"]["rate_date"] == "2026-01-05"


def test_failed_calculation_does_not_commit_month_lock(tmp_path, monkeypatch):
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    svc._daily_fx_snapshot_service.upsert_snapshot(
        rate_date="2026-01-05",
        cny_tt_buy=1.1,
        eur_tt_buy=9.0,
        usd_tt_sell=7.2,
        jpy_tt_sell=0.05,
        usd_tt_buy=7.1,
        actor="tester",
    )

    def fake_calculate_service_fees(*_args, **_kwargs):
        raise ValueError("contract parse failed")

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    with pytest.raises(HTTPException):
        svc.process_local_file(str(src), src.name)

    assert svc._daily_fx_snapshot_service.get_month_lock("2026-01") is None


def test_failed_stats_update_commits_month_lock_before_stats_write(tmp_path, monkeypatch):
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    svc._daily_fx_snapshot_service.upsert_snapshot(
        rate_date="2026-01-05",
        cny_tt_buy=1.1,
        eur_tt_buy=9.0,
        usd_tt_sell=7.2,
        jpy_tt_sell=0.05,
        usd_tt_buy=7.1,
        actor="tester",
    )

    def fake_calculate_service_fees(*_args, **_kwargs):
        out_path = uploads_dir / "calc_results.xlsx"
        pd.DataFrame(
            [{"母公司": "测试客户A", "代投消耗": 1000, "流水消耗": 0, "服务费": 100, "固定服务费": 0}]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)
    monkeypatch.setattr(svc, "_update_stats_from_result", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("stats failed")))

    with pytest.raises(RuntimeError):
        svc.process_local_file(str(src), src.name)

    locked_snapshot = svc._daily_fx_snapshot_service.get_month_lock("2026-01")
    assert locked_snapshot is not None
    assert locked_snapshot["rate_date"] == "2026-01-05"


def test_fx_lock_conflict_happens_before_stats_write(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "2026-01-consumption.xlsx"
    _write_sheet(src, "USD", [{"client": "A", "media": "Google", "managed": 1000}])

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)

    existing_snapshot = {
        "rate_date": "2026-01-05",
        "cny_tt_buy": 1.1,
        "eur_tt_buy": 9.0,
        "usd_tt_sell": 7.2,
        "jpy_tt_sell": 0.05,
        "usd_tt_buy": 7.1,
        "source": "manual",
        "pub_time": "2026-01-05 09:30:00",
    }
    pending_snapshot = {
        **existing_snapshot,
        "rate_date": "2026-01-06",
        "cny_tt_buy": 1.2,
    }
    svc._daily_fx_snapshot_service.lock_month_snapshot("2026-01", existing_snapshot, actor="tester")

    def fake_calculate_service_fees(*_args, **_kwargs):
        out_path = uploads_dir / "calc_results.xlsx"
        pd.DataFrame([{"client": "A", "service_fee": 100}]).to_excel(out_path, index=False)
        return str(out_path)

    stats_called = {"value": False}

    def fake_update_stats(*_args, **_kwargs):
        stats_called["value"] = True

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)
    monkeypatch.setattr(svc, "_update_stats_from_result", fake_update_stats)

    with pytest.raises(HTTPException) as exc:
        svc._run_calculation_core(
            str(src),
            src.name,
            persist_stats=True,
            require_fx_snapshot=True,
            exchange_context={
                "hangseng_today": pending_snapshot,
                "fx_lock": {
                    "status": "pending_create",
                    "month": "2026-01",
                    "rate_date": "2026-01-06",
                    "required_currencies": ["RMB"],
                    "actor": "tester",
                },
            },
        )

    assert exc.value.status_code == 409
    assert stats_called["value"] is False


def test_locked_month_snapshot_must_include_required_currency_fields(tmp_path, monkeypatch):
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    svc._daily_fx_snapshot_service.lock_month_snapshot(
        "2026-01",
        {
            "rate_date": "2026-01-05",
            "cny_tt_buy": 1.1,
            "usd_tt_sell": 7.2,
            "jpy_tt_sell": 0.05,
            "usd_tt_buy": 7.1,
            "source": "manual",
            "pub_time": "2026-01-05 09:30:00",
        },
        actor="tester",
    )
    monkeypatch.setattr(
        svc._daily_fx_snapshot_service,
        "get_today_snapshot",
        lambda: {
            "rate_date": "2026-01-06",
            "cny_tt_buy": 1.1,
            "eur_tt_buy": 9.0,
            "usd_tt_sell": 7.2,
            "jpy_tt_sell": 0.05,
            "usd_tt_buy": 7.1,
            "source": "manual",
            "pub_time": "2026-01-06 09:30:00",
        },
    )

    with pytest.raises(HTTPException) as exc:
        svc.process_local_file(str(src), src.name)

    assert exc.value.status_code == 400
    assert "EUR:eur_tt_buy" in str(exc.value.detail)
    assert svc._daily_fx_snapshot_service.get_month_lock("2026-01")["rate_date"] == "2026-01-05"


def test_foreign_currency_without_month_is_rejected_for_fx_lock(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "consumption.xlsx"
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

    svc = _service_with_isolated_fx_state(uploads_dir)
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    monkeypatch.setattr(
        svc._daily_fx_snapshot_service,
        "get_today_snapshot",
        lambda: {
            "rate_date": "2026-01-05",
            "cny_tt_buy": 1.1,
            "eur_tt_buy": 9.0,
            "usd_tt_sell": 7.2,
            "jpy_tt_sell": 0.05,
            "usd_tt_buy": 7.1,
            "source": "manual",
            "pub_time": "2026-01-05 09:30:00",
        },
    )

    with pytest.raises(HTTPException) as exc:
        svc.process_local_file(str(src), src.name)

    assert exc.value.status_code == 400
    assert "无法识别账期月份" in str(exc.value.detail)


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

    svc = _service_with_isolated_fx_state(uploads_dir)
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

    svc = _service_with_isolated_fx_state(uploads_dir)
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


def test_validate_estimate_workbook_accepts_service_type_and_summary_headers(tmp_path):
    src = tmp_path / "投放与毛利预估-导入.xlsx"
    _write_workbook(
        src,
        {
            "Sheet3": [
                {
                    "母公司": "Acmer",
                    "媒介": "Facebook",
                    "服务类型": "代投",
                    "求和项:26.4月消耗（04.01-04.30）": 21690.73,
                    "求和项:自然季度Q2预估毛利（04.01-04.30）": 542.27,
                }
            ]
        },
    )

    svc = CalculationService()
    svc._validate_estimate_workbook(str(src))


def test_process_estimate_with_service_type_and_summary_headers(tmp_path, monkeypatch):
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    src = tmp_path / "投放与毛利预估-导入.xlsx"
    _write_workbook(
        src,
        {
            "Sheet3": [
                {
                    "母公司": "Acmer",
                    "媒介": "Facebook",
                    "服务类型": "代投",
                    "求和项:26.4月消耗（04.01-04.30）": 21690.73,
                    "求和项:自然季度Q2预估毛利（04.01-04.30）": 542.27,
                }
            ]
        },
    )

    svc = CalculationService()
    monkeypatch.setattr(svc, "_get_upload_dir", lambda: uploads_dir)
    captured_kwargs = {}

    def fake_calculate_service_fees(*_args, **_kwargs):
        captured_kwargs.update(_kwargs)
        out_path = uploads_dir / "temp_result.xlsx"
        pd.DataFrame(
            [
                {
                    "母公司": "Acmer",
                    "服务类型": "代投",
                    "媒介": "Facebook",
                    "服务费": 100,
                    "固定服务费": 0,
                }
            ]
        ).to_excel(out_path, index=False)
        return str(out_path)

    monkeypatch.setattr("api.services.calculation_service.calculate_service_fees", fake_calculate_service_fees)

    result = svc.process_estimate_local_file(str(src), src.name)

    assert result["status"] == "ok"
    assert result["output_file"].endswith("_estimate_results.xlsx")
    assert captured_kwargs["calculation_date"] == "2026-04"


def test_parse_estimate_month_from_two_digit_dynamic_consumption_column():
    svc = CalculationService()

    assert svc._parse_month_from_estimate_column("求和项:26.5月消耗") == "2026-05"
    assert svc._parse_month_from_estimate_column("求和项:26.4月消耗（04.01-04.30）") == "2026-04"
    assert svc._parse_month_from_estimate_column("求和项:2026年4月消耗") == "2026-04"
