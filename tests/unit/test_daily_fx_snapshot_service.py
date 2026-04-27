# -*- coding: utf-8 -*-
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from api.services.daily_fx_snapshot_service import DailyFxSnapshotService


def _fixed_now():
    return datetime(2026, 3, 16, 9, 31, tzinfo=ZoneInfo("Asia/Shanghai"))


def test_upsert_snapshot_marks_manual_source(tmp_path, monkeypatch):
    state_path = tmp_path / "hangseng_daily_fx_state.json"
    service = DailyFxSnapshotService(state_path=state_path)

    monkeypatch.setattr(service, "_now", _fixed_now)

    snapshot = service.upsert_snapshot(
        rate_date="2026-03-16",
        cny_tt_buy=1.1,
        eur_tt_buy=8.9,
        usd_tt_sell=7.2,
        jpy_tt_sell=0.05,
        usd_tt_buy=7.1,
    )

    assert snapshot["source"] == "manual"
    assert snapshot["eur_tt_buy"] == 8.9

    payload = service.get_today_snapshot_payload()
    assert payload["has_snapshot"] is True
    assert payload["snapshot"]["eur_tt_buy"] == 8.9


def test_upsert_snapshot_rejects_invalid_date(tmp_path, monkeypatch):
    state_path = tmp_path / "hangseng_daily_fx_state.json"
    service = DailyFxSnapshotService(state_path=state_path)
    monkeypatch.setattr(service, "_now", _fixed_now)

    with pytest.raises(ValueError, match="Invalid rate_date"):
        service.upsert_snapshot(
            rate_date="not-a-date",
            cny_tt_buy=1.1,
            eur_tt_buy=8.9,
            usd_tt_sell=7.2,
            jpy_tt_sell=0.05,
            usd_tt_buy=7.1,
        )


def test_upsert_snapshot_rejects_zero_value(tmp_path, monkeypatch):
    state_path = tmp_path / "hangseng_daily_fx_state.json"
    service = DailyFxSnapshotService(state_path=state_path)
    monkeypatch.setattr(service, "_now", _fixed_now)

    with pytest.raises(ValueError, match="must be positive"):
        service.upsert_snapshot(
            rate_date="2026-03-16",
            cny_tt_buy=0,
            eur_tt_buy=8.9,
            usd_tt_sell=7.2,
            jpy_tt_sell=0.05,
            usd_tt_buy=7.1,
        )


def test_get_today_snapshot_returns_none_when_empty(tmp_path, monkeypatch):
    state_path = tmp_path / "hangseng_daily_fx_state.json"
    service = DailyFxSnapshotService(state_path=state_path)
    monkeypatch.setattr(service, "_now", _fixed_now)

    assert service.get_today_snapshot() is None

    payload = service.get_today_snapshot_payload()
    assert payload["has_snapshot"] is False
    assert payload["snapshot"] is None


def test_list_snapshots_returns_sorted(tmp_path, monkeypatch):
    state_path = tmp_path / "hangseng_daily_fx_state.json"
    service = DailyFxSnapshotService(state_path=state_path)
    monkeypatch.setattr(service, "_now", _fixed_now)

    service.upsert_snapshot(rate_date="2026-03-14", cny_tt_buy=1.1, eur_tt_buy=8.9, usd_tt_sell=7.2, jpy_tt_sell=0.05, usd_tt_buy=7.1)
    service.upsert_snapshot(rate_date="2026-03-16", cny_tt_buy=1.12, eur_tt_buy=9.1, usd_tt_sell=7.3, jpy_tt_sell=0.051, usd_tt_buy=7.2)
    service.upsert_snapshot(rate_date="2026-03-15", cny_tt_buy=1.11, eur_tt_buy=9.0, usd_tt_sell=7.25, jpy_tt_sell=0.0505, usd_tt_buy=7.15)

    items = service.list_snapshots(limit=10)
    assert len(items) == 3
    assert items[0]["date"] == "2026-03-16"
    assert items[0]["eur_tt_buy"] == 9.1
    assert items[1]["date"] == "2026-03-15"
    assert items[2]["date"] == "2026-03-14"


def test_save_state_retries_on_permission_error(tmp_path, monkeypatch):
    state_path = tmp_path / "hangseng_daily_fx_state.json"
    service = DailyFxSnapshotService(state_path=state_path)

    original_replace = type(state_path).replace
    calls = {"count": 0}

    def flaky_replace(self, target):
        calls["count"] += 1
        if calls["count"] == 1:
            raise PermissionError("[WinError 5] access denied")
        return original_replace(self, target)

    monkeypatch.setattr(type(state_path), "replace", flaky_replace)

    service._save_state_unlocked(service._default_state())

    assert state_path.exists()
    assert calls["count"] >= 2
