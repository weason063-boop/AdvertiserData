from api.auth import get_current_user_info
from api.main import app
import api.routers.calculation as calculation_router


USER_WITH_BILLING = {
    "id": 10,
    "username": "operator_a",
    "role": "user",
    "permissions": ["billing_run"],
}

ADMIN_USER = {
    "id": 11,
    "username": "admin_a",
    "role": "admin",
    "permissions": [],
}

SUPER_ADMIN_USER = {
    "id": 12,
    "username": "super_a",
    "role": "super_admin",
    "permissions": [],
}

READONLY_USER = {
    "id": 13,
    "username": "viewer_a",
    "role": "user",
    "permissions": [],
}


def _override_current_user_info(payload: dict):
    app.dependency_overrides[get_current_user_info] = lambda: payload


def _clear_overrides():
    app.dependency_overrides.pop(get_current_user_info, None)


def test_task_history_requires_admin_role_for_billing_user(client):
    _override_current_user_info(USER_WITH_BILLING)
    try:
        response = client.get("/api/task-history")
        assert response.status_code == 403
    finally:
        _clear_overrides()


def test_task_history_requires_admin_role_for_readonly_user(client):
    _override_current_user_info(READONLY_USER)
    try:
        response = client.get("/api/task-history")
        assert response.status_code == 403
    finally:
        _clear_overrides()


def test_task_history_admin_can_query_global_records(client, monkeypatch):
    captured: dict = {}

    def _fake_list_operation_audit_logs(**kwargs):
        captured.update(kwargs)
        return [
            {
                "id": 1,
                "category": "billing",
                "action": "calculate",
                "actor": "operator_a",
                "status": "success",
                "created_at": "2026-03-23 10:00:00",
            }
        ]

    monkeypatch.setattr(calculation_router, "list_operation_audit_logs", _fake_list_operation_audit_logs)
    _override_current_user_info(ADMIN_USER)

    try:
        response = client.get("/api/task-history?limit=50&action=calculate&status=success")
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        assert payload["items"][0]["actor"] == "operator_a"
        assert captured["limit"] == 50
        assert captured["actor"] is None
        assert captured["action"] == "calculate"
        assert captured["status"] == "success"
        assert captured["category"] is None
    finally:
        _clear_overrides()


def test_task_history_super_admin_is_allowed(client, monkeypatch):
    captured: dict = {}

    def _fake_list_operation_audit_logs(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(calculation_router, "list_operation_audit_logs", _fake_list_operation_audit_logs)
    _override_current_user_info(SUPER_ADMIN_USER)

    try:
        response = client.get("/api/task-history?limit=20&category=fx")
        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 0
        assert captured["limit"] == 20
        assert captured["actor"] is None
        assert captured["category"] == "fx"
        assert captured["action"] is None
        assert captured["status"] is None
    finally:
        _clear_overrides()


def test_task_history_passes_days_filter_to_query(client, monkeypatch):
    captured: dict = {}

    def _fake_list_operation_audit_logs(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(calculation_router, "list_operation_audit_logs", _fake_list_operation_audit_logs)
    _override_current_user_info(ADMIN_USER)

    try:
        response = client.get("/api/task-history?days=7")
        assert response.status_code == 200
        assert captured["actor"] is None
        assert captured["created_after"] is not None
    finally:
        _clear_overrides()


def test_task_history_export_requires_admin_role(client):
    _override_current_user_info(USER_WITH_BILLING)
    try:
        response = client.get("/api/task-history/export")
        assert response.status_code == 403
    finally:
        _clear_overrides()


def test_task_history_export_returns_csv(client, monkeypatch):
    captured: dict = {}

    def _fake_list_operation_audit_logs(**kwargs):
        captured.update(kwargs)
        return [
            {
                "id": 99,
                "created_at": "2026-03-23 11:22:33",
                "category": "billing",
                "action": "calculate",
                "status": "success",
                "actor": "operator_a",
                "input_file": "in.xlsx",
                "output_file": "out.xlsx",
                "result_ref": "result_abc",
                "error_message": None,
            }
        ]

    monkeypatch.setattr(calculation_router, "list_operation_audit_logs", _fake_list_operation_audit_logs)
    _override_current_user_info(ADMIN_USER)

    try:
        response = client.get("/api/task-history/export?limit=100&action=calculate&days=30")
        assert response.status_code == 200
        assert "text/csv" in (response.headers.get("content-type") or "")
        assert "attachment;" in (response.headers.get("content-disposition") or "")

        csv_text = response.content.decode("utf-8-sig")
        assert "id,created_at,category,action,status,actor" in csv_text
        assert "99,2026-03-23 11:22:33,billing,calculate,success,operator_a" in csv_text
        assert captured["actor"] is None
        assert captured["action"] == "calculate"
        assert captured["created_after"] is not None
    finally:
        _clear_overrides()


def test_task_history_passes_actor_filter(client, monkeypatch):
    captured: dict = {}

    def _fake_list_operation_audit_logs(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(calculation_router, "list_operation_audit_logs", _fake_list_operation_audit_logs)
    _override_current_user_info(ADMIN_USER)

    try:
        response = client.get("/api/task-history?actor=alice")
        assert response.status_code == 200
        assert captured["actor"] is None
        assert captured["actor_like"] == "alice"
    finally:
        _clear_overrides()


def test_task_history_export_passes_actor_filter(client, monkeypatch):
    captured: dict = {}

    def _fake_list_operation_audit_logs(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr(calculation_router, "list_operation_audit_logs", _fake_list_operation_audit_logs)
    _override_current_user_info(ADMIN_USER)

    try:
        response = client.get("/api/task-history/export?actor=alice")
        assert response.status_code == 200
        assert captured["actor"] is None
        assert captured["actor_like"] == "alice"
    finally:
        _clear_overrides()
