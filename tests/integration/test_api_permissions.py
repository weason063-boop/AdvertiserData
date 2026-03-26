from api.auth import get_current_user_info
from api.main import app


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


def test_download_rejects_non_result_filename(client):
    _override_current_user_info(BILLING_USER)
    response = client.get("/api/download/.env")
    assert response.status_code == 400
    _clear_overrides()
