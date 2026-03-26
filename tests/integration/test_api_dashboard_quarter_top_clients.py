from api.auth import get_current_user
from api.main import app
from api.database import upsert_client_stats_batch


def _override_auth(username: str = "dashboard_tester"):
    app.dependency_overrides[get_current_user] = lambda: username


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user, None)


def _seed_quarter_stats(db_session):
    upsert_client_stats_batch(
        "2025-03",
        [
            {"name": "Alpha", "consumption": 50, "fee": 5},
            {"name": "Beta", "consumption": 30, "fee": 3},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2025-04",
        [
            {"name": "Alpha", "consumption": 60, "fee": 6},
            {"name": "Beta", "consumption": 20, "fee": 2},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2025-05",
        [
            {"name": "Alpha", "consumption": 70, "fee": 7},
            {"name": "Beta", "consumption": 10, "fee": 1},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2025-12",
        [
            {"name": "Alpha", "consumption": 40, "fee": 4},
            {"name": "Beta", "consumption": 50, "fee": 5},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-01",
        [
            {"name": "Alpha", "consumption": 40, "fee": 4},
            {"name": "Beta", "consumption": 50, "fee": 5},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-02",
        [
            {"name": "Alpha", "consumption": 40, "fee": 4},
            {"name": "Beta", "consumption": 50, "fee": 5},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-03",
        [
            {"name": "Alpha", "consumption": 100, "fee": 10},
            {"name": "Beta", "consumption": 80, "fee": 8},
            {"name": "Gamma", "consumption": 20, "fee": 2},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-04",
        [
            {"name": "Alpha", "consumption": 110, "fee": 11},
            {"name": "Beta", "consumption": 70, "fee": 7},
            {"name": "Gamma", "consumption": 30, "fee": 3},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-05",
        [
            {"name": "Alpha", "consumption": 90, "fee": 9},
            {"name": "Beta", "consumption": 90, "fee": 9},
            {"name": "Gamma", "consumption": 40, "fee": 4},
        ],
        db=db_session,
    )


def test_quarter_top_clients_supports_dual_compare_mode(client, db_session):
    _seed_quarter_stats(db_session)
    _override_auth()

    response = client.get("/api/dashboard/quarter/2026-Q1/top-clients?limit=10&compare_mode=dual")

    assert response.status_code == 200
    payload = response.json()
    assert payload["quarter"] == "2026-Q1"
    assert payload["compare_mode"] == "dual"
    assert payload["prev_quarter"] == "2025-Q4"
    assert payload["yoy_quarter"] == "2025-Q1"

    alpha = next(item for item in payload["clients"] if item["client_name"] == "Alpha")
    assert alpha["prev_quarter_consumption"] == 120.0
    assert alpha["yoy_consumption"] == 180.0
    assert alpha["qoq_delta"] == 180.0
    assert alpha["yoy_delta"] == 120.0
    _clear_overrides()


def test_quarter_top_clients_supports_qoq_compare_mode(client, db_session):
    _seed_quarter_stats(db_session)
    _override_auth()

    response = client.get("/api/dashboard/quarter/2026-Q1/top-clients?limit=10&compare_mode=qoq")

    assert response.status_code == 200
    payload = response.json()
    assert payload["compare_mode"] == "qoq"
    beta = next(item for item in payload["clients"] if item["client_name"] == "Beta")
    assert beta["prev_quarter_consumption"] == 150.0
    assert beta["consumption_delta"] == 90.0
    assert beta["rank_change"] == -1
    _clear_overrides()


def test_quarter_top_clients_keeps_compare_prev_compatibility(client, db_session):
    _seed_quarter_stats(db_session)
    _override_auth()

    response = client.get("/api/dashboard/quarter/2026-Q1/top-clients?limit=10&compare_prev=true")

    assert response.status_code == 200
    payload = response.json()
    assert payload["compare_mode"] == "qoq"
    alpha = next(item for item in payload["clients"] if item["client_name"] == "Alpha")
    assert alpha["prev_consumption"] == 120.0
    assert alpha["consumption_delta"] == 180.0
    assert alpha["rank_change"] == 1
    _clear_overrides()
