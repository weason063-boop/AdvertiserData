from api.auth import get_current_user
from api.database import upsert_client_stats_batch
from api.main import app


def _override_auth(username: str = "dashboard_tester"):
    app.dependency_overrides[get_current_user] = lambda: username


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user, None)


def _seed_month_stats(db_session):
    upsert_client_stats_batch(
        "2025-02",
        [
            {"name": "Alpha", "consumption": 120, "fee": 12},
            {"name": "Beta", "consumption": 20, "fee": 2},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-01",
        [
            {"name": "Alpha", "consumption": 90, "fee": 9},
            {"name": "Beta", "consumption": 110, "fee": 11},
            {"name": "Gamma", "consumption": 40, "fee": 4},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-02",
        [
            {"name": "Alpha", "consumption": 150, "fee": 15},
            {"name": "Beta", "consumption": 80, "fee": 8},
            {"name": "Gamma", "consumption": 60, "fee": 6},
        ],
        db=db_session,
    )


def test_month_top_clients_supports_dual_compare_mode(client, db_session):
    _seed_month_stats(db_session)
    _override_auth()

    response = client.get("/api/dashboard/month/2026-02/top-clients?limit=10&compare_mode=dual")

    assert response.status_code == 200
    payload = response.json()
    assert payload["month"] == "2026-02"
    assert payload["compare_mode"] == "dual"
    assert payload["prev_month"] == "2026-01"
    assert payload["yoy_month"] == "2025-02"

    alpha = next(item for item in payload["clients"] if item["client_name"] == "Alpha")
    gamma = next(item for item in payload["clients"] if item["client_name"] == "Gamma")

    assert alpha["prev_month_consumption"] == 90.0
    assert alpha["yoy_consumption"] == 120.0
    assert alpha["mom_delta"] == 60.0
    assert alpha["yoy_delta"] == 30.0
    assert alpha["mom_rank_change"] == 1
    assert alpha["yoy_rank_change"] == 0

    assert gamma["prev_month_consumption"] == 40.0
    assert gamma["yoy_consumption"] is None
    assert gamma["mom_delta"] == 20.0
    assert gamma["yoy_delta"] is None
    _clear_overrides()


def test_month_top_clients_supports_yoy_compare_mode(client, db_session):
    _seed_month_stats(db_session)
    _override_auth()

    response = client.get("/api/dashboard/month/2026-02/top-clients?limit=10&compare_mode=yoy")

    assert response.status_code == 200
    payload = response.json()
    assert payload["compare_mode"] == "yoy"
    assert payload["yoy_month"] == "2025-02"
    beta = next(item for item in payload["clients"] if item["client_name"] == "Beta")
    assert beta["yoy_consumption"] == 20.0
    assert beta["yoy_delta"] == 60.0
    _clear_overrides()


def test_month_top_clients_keeps_compare_prev_compatibility(client, db_session):
    _seed_month_stats(db_session)
    _override_auth()

    response = client.get("/api/dashboard/month/2026-02/top-clients?limit=10&compare_prev=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["compare_mode"] == "mom"
    alpha = next(item for item in payload["clients"] if item["client_name"] == "Alpha")
    assert alpha["prev_consumption"] == 90.0
    assert alpha["consumption_delta"] == 60.0
    assert alpha["rank_change"] == 1
    _clear_overrides()
