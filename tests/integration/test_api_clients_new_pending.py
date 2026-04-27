import json

from api.auth import get_current_user, get_current_user_info
from api.main import app
from api.models import Client, ClientContractChangeReview


FULL_PERMISSION_USER = {
    "id": 1,
    "username": "tester",
    "role": "super_admin",
    "permissions": ["client_write", "feishu_sync", "billing_run"],
}


def _override_auth(payload: dict):
    app.dependency_overrides[get_current_user] = lambda: payload["username"]
    app.dependency_overrides[get_current_user_info] = lambda: payload


def _clear_auth_override():
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_info, None)


def test_approve_contract_change_review_creates_new_client_when_missing(client, db_session):
    review = ClientContractChangeReview(
        client_name="Approve New Client",
        source_type="feishu_sheet",
        source_token="sheet-new-client",
        sync_batch_id="batch-new-client",
        status="pending",
        change_fields_json=json.dumps(["business_type", "department", "entity", "fee_clause", "payment_term"]),
        new_business_type="AD",
        new_department="North",
        new_entity="New Entity",
        new_fee_clause="New Client Clause",
        new_payment_term="N15",
    )
    db_session.add(review)
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.post(f"/api/clients/contract-change-reviews/{review.id}/approve")

    assert response.status_code == 200
    created_client = db_session.query(Client).filter(Client.name == "Approve New Client").first()
    db_session.refresh(review)
    assert created_client is not None
    assert created_client.business_type == "AD"
    assert created_client.department == "North"
    assert created_client.entity == "New Entity"
    assert created_client.fee_clause == "New Client Clause"
    assert created_client.payment_term == "N15"
    assert review.status == "approved"
    _clear_auth_override()
