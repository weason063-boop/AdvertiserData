import pytest

from api.auth import get_current_user, get_current_user_info
from api.main import app
from api.models import Client


FULL_PERMISSION_USER = {
    "id": 1,
    "username": "tester",
    "role": "super_admin",
    "permissions": ["client_write", "feishu_sync", "billing_run"],
}
READONLY_USER = {
    "id": 2,
    "username": "readonly",
    "role": "user",
    "permissions": [],
}


def _override_auth(payload: dict):
    app.dependency_overrides[get_current_user] = lambda: payload["username"]
    app.dependency_overrides[get_current_user_info] = lambda: payload


def _clear_auth_override():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_info, None)


def test_get_clients(client, db_session):
    db_session.add(Client(name="Client A", fee_clause="10%"))
    db_session.add(Client(name="Client B", fee_clause="5%"))
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.get("/api/clients/")

    assert response.status_code == 200
    data = response.json()
    assert len(data["clients"]) >= 2
    names = [c["name"] for c in data["clients"]]
    assert "Client A" in names
    assert "Client B" in names
    _clear_auth_override()


def test_update_client_clause(client, db_session):
    target = Client(name="Update Me", fee_clause="Old Clause")
    db_session.add(target)
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.put(f"/api/clients/{target.id}", json={"fee_clause": "New Clause"})

    assert response.status_code == 200
    db_session.refresh(target)
    assert target.fee_clause == "New Clause"
    _clear_auth_override()


def test_update_client_clause_forbidden_without_permission(client, db_session):
    target = Client(name="Readonly", fee_clause="Old Clause")
    db_session.add(target)
    db_session.commit()

    _override_auth(READONLY_USER)
    response = client.put(f"/api/clients/{target.id}", json={"fee_clause": "New Clause"})

    assert response.status_code == 403
    _clear_auth_override()


def test_create_client(client, db_session):
    _override_auth(FULL_PERMISSION_USER)
    response = client.post(
        "/api/clients",
        json={
            "name": "New Test Client",
            "business_type": "IT",
            "fee_clause": "20% fee",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"

    client_db = db_session.query(Client).filter_by(name="New Test Client").first()
    assert client_db is not None
    assert client_db.fee_clause == "20% fee"
    _clear_auth_override()


def test_sync_feishu_trigger(client):
    pytest.skip("External integration test is intentionally skipped in unit CI.")
