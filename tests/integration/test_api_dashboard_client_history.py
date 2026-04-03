from api.auth import get_current_user
from api.database import upsert_client_detail_stats_batch, upsert_client_stats_batch
from api.main import app
from api.models import Client


def _override_auth(username: str = "dashboard_history_tester"):
    app.dependency_overrides[get_current_user] = lambda: username


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user, None)


def test_latest_month_clients_requires_auth(client, db_session):
    upsert_client_stats_batch(
        "2026-02",
        [{"name": "Alpha", "consumption": 100, "fee": 10}],
        db=db_session,
    )

    response = client.get("/api/dashboard/latest-month/clients")

    assert response.status_code == 401


def test_latest_month_clients_returns_latest_month_rows(client, db_session):
    upsert_client_stats_batch(
        "2026-01",
        [
            {"name": "Alpha", "consumption": 80, "fee": 8},
            {"name": "Beta", "consumption": 60, "fee": 6},
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-02",
        [
            {"name": "Alpha", "consumption": 120, "fee": 12},
            {"name": "Gamma", "consumption": 90, "fee": 9},
        ],
        db=db_session,
    )
    _override_auth()

    response = client.get("/api/dashboard/latest-month/clients")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_month"] == "2026-02"
    assert [item["client_name"] for item in payload["rows"]] == ["Alpha", "Gamma"]
    assert payload["rows"][0]["month"] == "2026-02"
    assert payload["rows"][0]["bill_amount"] == 132.0
    assert payload["rows"][0]["note"] is None
    _clear_overrides()


def test_latest_month_clients_returns_detail_metrics_when_available(client, db_session):
    db_session.add(
        Client(
            name="Alpha",
            business_type="Agency",
            department="Nora",
            entity="Entity-A",
            fee_clause="5%",
        )
    )
    db_session.commit()

    upsert_client_detail_stats_batch(
        "2026-02",
        [
            {
                "name": "Alpha",
                "bill_type": "预付",
                "service_type": "代投",
                "flow_consumption": 90,
                "managed_consumption": 60,
                "net_consumption": 145,
                "service_fee": 8,
                "fixed_service_fee": 2,
                "coupon": -5,
                "dst": 3,
                "total": 155,
            }
        ],
        db=db_session,
    )
    _override_auth()

    response = client.get("/api/dashboard/latest-month/clients")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_month"] == "2026-02"
    assert payload["rows"][0]["bill_type"] == "预付"
    assert payload["rows"][0]["service_type"] == "代投"
    assert payload["rows"][0]["fixed_service_fee"] == 2.0
    assert payload["rows"][0]["total"] == 155.0
    assert payload["rows"][0]["month"] == "2026-02"
    assert payload["rows"][0]["entity"] == "Entity-A"
    assert payload["rows"][0]["owner"] == "Nora"
    assert payload["rows"][0]["bill_amount"] == 155.0
    assert payload["rows"][0]["note"] is None
    _clear_overrides()


def test_update_latest_month_client_note_requires_auth(client, db_session):
    response = client.put(
        "/api/dashboard/latest-month/client-note",
        json={"month": "2026-02", "client_name": "Alpha", "note": "测试备注"},
    )

    assert response.status_code == 401


def test_update_latest_month_client_note_success(client, db_session):
    upsert_client_stats_batch(
        "2026-02",
        [{"name": "Alpha", "consumption": 120, "fee": 12}],
        db=db_session,
    )
    _override_auth()

    save_response = client.put(
        "/api/dashboard/latest-month/client-note",
        json={"month": "2026-02", "client_name": "Alpha", "note": "请核对账单"},
    )

    assert save_response.status_code == 200
    assert save_response.json()["note"] == "请核对账单"

    latest_response = client.get("/api/dashboard/latest-month/clients")
    assert latest_response.status_code == 200
    assert latest_response.json()["rows"][0]["note"] == "请核对账单"
    _clear_overrides()


def test_client_history_returns_profile_and_rows(client, db_session):
    db_session.add(
        Client(
            name="Alpha",
            business_type="Agency",
            department="North",
            entity="Entity-A",
            fee_clause="5%",
        )
    )
    db_session.commit()

    upsert_client_stats_batch(
        "2025-12",
        [{"name": "Alpha", "consumption": 100, "fee": 10}],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2026-01",
        [{"name": "Alpha", "consumption": 110, "fee": 11}],
        db=db_session,
    )
    _override_auth()

    response = client.get("/api/dashboard/client/Alpha/history")

    assert response.status_code == 200
    payload = response.json()
    assert payload["profile"]["client_name"] == "Alpha"
    assert payload["profile"]["entity"] == "Entity-A"
    assert [item["month"] for item in payload["rows"]] == ["2026-01", "2025-12"]
    assert payload["summary"]["total_consumption"] == 210.0
    assert payload["summary"]["total_service_fee"] == 21.0
    _clear_overrides()


def test_client_history_returns_detail_rows_and_summary_fields(client, db_session):
    db_session.add(
        Client(
            name="Alpha",
            business_type="Agency",
            department="North",
            entity="Entity-A",
            fee_clause="5%",
        )
    )
    db_session.commit()

    upsert_client_detail_stats_batch(
        "2026-02",
        [
            {
                "name": "Alpha",
                "bill_type": "预付",
                "service_type": "代投",
                "flow_consumption": 80,
                "managed_consumption": 20,
                "net_consumption": 96,
                "service_fee": 5,
                "fixed_service_fee": 1,
                "coupon": -2,
                "dst": 3,
                "total": 103,
            }
        ],
        db=db_session,
    )
    upsert_client_stats_batch(
        "2025-12",
        [{"name": "Alpha", "consumption": 90, "fee": 9}],
        db=db_session,
    )
    _override_auth()

    response = client.get("/api/dashboard/client/Alpha/history")

    assert response.status_code == 200
    payload = response.json()
    assert [item["month"] for item in payload["rows"]] == ["2026-02", "2025-12"]
    assert payload["rows"][0]["bill_type"] == "预付"
    assert payload["rows"][0]["dst"] == 3.0
    assert payload["summary"]["total_service_fee"] == 15.0
    assert payload["summary"]["total_total"] == 202.0
    _clear_overrides()
