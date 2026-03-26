# -*- coding: utf-8 -*-

import pytest
from fastapi import HTTPException

from api.services.calculation_service import CalculationService
from calculate_service_fee import build_cli_exchange_context


def test_cli_context_skips_snapshot_for_usd_only(monkeypatch):
    monkeypatch.setattr(CalculationService, "_parse_month_from_filename", lambda self, _filename: "2026-01")
    monkeypatch.setattr(CalculationService, "_contains_rmb_consumption", lambda self, _path: False)
    monkeypatch.setattr(CalculationService, "_contains_jpy_consumption", lambda self, _path: False)
    monkeypatch.setattr(CalculationService, "_build_daily_exchange_context", lambda self, require_snapshot: {"hangseng_today": {}})

    month, context = build_cli_exchange_context("dummy.xlsx", "2026-01-consumption.xlsx")

    assert month == "2026-01"
    assert context["hangseng_today"] == {}


def test_cli_context_reports_missing_daily_snapshot(monkeypatch):
    monkeypatch.setattr(CalculationService, "_parse_month_from_filename", lambda self, _filename: "2026-01")
    monkeypatch.setattr(CalculationService, "_contains_rmb_consumption", lambda self, _path: False)
    monkeypatch.setattr(CalculationService, "_contains_jpy_consumption", lambda self, _path: True)

    def _raise_missing(self, require_snapshot: bool):
        assert require_snapshot is True
        raise HTTPException(status_code=400, detail="今日恒生汇率快照尚未生效")

    monkeypatch.setattr(CalculationService, "_build_daily_exchange_context", _raise_missing)

    with pytest.raises(HTTPException) as exc:
        build_cli_exchange_context("dummy.xlsx", "2026-01-consumption.xlsx")

    assert exc.value.status_code == 400
    assert "快照" in str(exc.value.detail)


def test_cli_context_collects_rmb_and_jpy_snapshot(monkeypatch):
    monkeypatch.setattr(CalculationService, "_parse_month_from_filename", lambda self, _filename: "2026-01")
    monkeypatch.setattr(CalculationService, "_contains_rmb_consumption", lambda self, _path: True)
    monkeypatch.setattr(CalculationService, "_contains_jpy_consumption", lambda self, _path: True)
    monkeypatch.setattr(
        CalculationService,
        "_build_daily_exchange_context",
        lambda self, require_snapshot: {
            "hangseng_today": {
                "cny_tt_buy": 1.1,
                "usd_tt_sell": 7.2,
                "jpy_tt_sell": 0.05,
                "usd_tt_buy": 7.1,
            }
        },
    )

    month, context = build_cli_exchange_context("dummy.xlsx", "2026-01-consumption.xlsx")

    assert month == "2026-01"
    assert context["hangseng_today"]["cny_tt_buy"] == 1.1
    assert context["hangseng_today"]["jpy_tt_sell"] == 0.05
