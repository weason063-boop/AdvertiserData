from datetime import date

from api.auth import get_current_user, get_current_user_info
from api.main import app
from api.routers.exchange_rates import daily_fx_service


BILLING_USER = {
    "id": 1,
    "username": "billing",
    "role": "user",
    "permissions": ["billing_run"],
}
READONLY_USER = {
    "id": 2,
    "username": "readonly",
    "role": "user",
    "permissions": [],
}


def _override_current_user(username: str):
    app.dependency_overrides[get_current_user] = lambda: username


def _override_current_user_info(payload: dict):
    app.dependency_overrides[get_current_user_info] = lambda: payload


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_info, None)


def test_daily_snapshot_requires_authentication(client, tmp_path, monkeypatch):
    monkeypatch.setattr(daily_fx_service, "_state_path_override", tmp_path / "daily_fx_state.json")

    response = client.get("/api/exchange-rates/daily-snapshot")

    assert response.status_code == 401


def test_upsert_daily_snapshot_requires_billing_permission(client, tmp_path, monkeypatch):
    monkeypatch.setattr(daily_fx_service, "_state_path_override", tmp_path / "daily_fx_state.json")
    _override_current_user_info(READONLY_USER)

    response = client.put(
        "/api/exchange-rates/daily-snapshots/2026-03-16",
        json={
            "cny_tt_buy": 1.1,
            "eur_tt_buy": 8.9,
            "usd_tt_sell": 7.2,
            "jpy_tt_sell": 0.05,
            "usd_tt_buy": 7.1,
        },
    )

    assert response.status_code == 403
    _clear_overrides()


def test_upsert_daily_snapshot_succeeds_for_billing_user(client, tmp_path, monkeypatch):
    today = date.today().isoformat()
    monkeypatch.setattr(daily_fx_service, "_state_path_override", tmp_path / "daily_fx_state.json")
    _override_current_user_info(BILLING_USER)

    response = client.put(
        f"/api/exchange-rates/daily-snapshots/{today}",
        json={
            "cny_tt_buy": 1.1,
            "eur_tt_buy": 8.9,
            "usd_tt_sell": 7.2,
            "jpy_tt_sell": 0.05,
            "usd_tt_buy": 7.1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["snapshot"]["source"] == "manual"
    assert body["snapshot"]["eur_tt_buy"] == 8.9

    _override_current_user("billing")
    snapshot_response = client.get("/api/exchange-rates/daily-snapshot")
    assert snapshot_response.status_code == 200
    payload = snapshot_response.json()
    assert payload["has_snapshot"] is True
    assert payload["snapshot"]["eur_tt_buy"] == 8.9

    history_response = client.get("/api/exchange-rates/daily-snapshots?limit=5")
    assert history_response.status_code == 200
    history_items = history_response.json()["items"]
    assert len(history_items) >= 1
    assert history_items[0]["eur_tt_buy"] == 8.9
    _clear_overrides()
