from api.auth import create_access_token, get_current_user_info
from api.main import app
from api.models import User


SUPER_ADMIN = {
    "id": 1,
    "username": "super",
    "role": "super_admin",
    "permissions": ["client_write", "feishu_sync", "billing_run"],
}
ADMIN = {
    "id": 2,
    "username": "admin",
    "role": "admin",
    "permissions": [],
}
READONLY = {
    "id": 3,
    "username": "readonly",
    "role": "user",
    "permissions": [],
}

BILLING_USER = {
    "id": 4,
    "username": "billing_user",
    "role": "user",
    "permissions": ["billing_run"],
}


def _override_current_user_info(payload: dict):
    app.dependency_overrides[get_current_user_info] = lambda: payload


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user_info, None)


def test_users_management_requires_super_admin(client):
    _override_current_user_info(ADMIN)
    response = client.get("/api/users")
    assert response.status_code == 403
    _clear_overrides()


def test_users_management_allows_super_admin(client):
    _override_current_user_info(SUPER_ADMIN)
    response = client.get("/api/users")
    assert response.status_code == 200
    _clear_overrides()


def test_recalculate_requires_billing_run_permission(client):
    _override_current_user_info(READONLY)
    response = client.post("/api/recalculate")
    assert response.status_code == 403
    _clear_overrides()


def test_estimate_calculate_requires_billing_run_permission(client):
    _override_current_user_info(READONLY)
    response = client.post(
        "/api/estimate/calculate",
        files={
            "file": (
                "estimate.xlsx",
                b"dummy",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 403
    _clear_overrides()


def test_estimate_recalculate_requires_billing_run_permission(client):
    _override_current_user_info(READONLY)
    response = client.post("/api/estimate/recalculate")
    assert response.status_code == 403
    _clear_overrides()


def test_estimate_latest_result_requires_billing_run_permission(client):
    _override_current_user_info(READONLY)
    response = client.get("/api/estimate/latest-result")
    assert response.status_code == 403
    _clear_overrides()


def test_download_rejects_non_result_filename(client):
    _override_current_user_info(BILLING_USER)
    response = client.get("/api/download/.env")
    assert response.status_code == 400
    _clear_overrides()


def test_deleted_user_token_cannot_access_authenticated_read_api(client, db_session):
    user = User(
        username="deleted_user",
        password_hash="not_used_in_this_test",
        role="user",
        permissions="[]",
    )
    db_session.add(user)
    db_session.commit()

    token = create_access_token({"sub": "deleted_user"})

    db_session.delete(user)
    db_session.commit()

    response = client.get(
        "/api/clients",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.json().get("detail") == "User not found"
