from api.auth import (
    BUSINESS_PERMISSIONS,
    get_role_permissions,
    has_permission,
    normalize_permissions,
)


def test_normalize_permissions_filters_unknown_values():
    result = normalize_permissions(["client_write", "CLIENT_WRITE", "unknown", "", "billing_run"])
    assert result == ["client_write", "billing_run"]


def test_get_role_permissions_for_admin_is_full_set():
    result = get_role_permissions("admin", "[]")
    assert result == list(BUSINESS_PERMISSIONS)


def test_get_role_permissions_for_user_uses_stored_json():
    result = get_role_permissions("user", "[\"billing_run\", \"invalid\"]")
    assert result == ["billing_run"]


def test_has_permission_for_user_without_grant_returns_false():
    current = {"role": "user", "permissions": ["client_write"]}
    assert has_permission(current, "billing_run") is False

