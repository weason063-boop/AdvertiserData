import json

import pytest

from api.auth import get_current_user, get_current_user_info
from api.main import app
from api.models import Client, ClientContractChangeReview


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


def test_get_clients_supports_searching_fee_clause(client, db_session):
    db_session.add(Client(name="Only Name Match A", fee_clause="返点 2% + 固定 100"))
    db_session.add(Client(name="Only Name Match B", fee_clause="监管费 3.5%"))
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.get("/api/clients/?search=监管费 3.5")

    assert response.status_code == 200
    data = response.json()
    names = [c["name"] for c in data["clients"]]
    assert "Only Name Match B" in names
    assert "Only Name Match A" not in names
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


def test_get_contract_change_reviews_returns_pending_only(client, db_session):
    db_session.add(
        ClientContractChangeReview(
            client_name="Alpha",
            source_type="feishu_sheet",
            source_token="sheet-1",
            sync_batch_id="batch-1",
            status="pending",
            change_fields_json=json.dumps(["fee_clause"]),
            current_fee_clause="旧条款",
            new_fee_clause="新条款",
        )
    )
    db_session.add(
        ClientContractChangeReview(
            client_name="Beta",
            source_type="feishu_sheet",
            source_token="sheet-1",
            sync_batch_id="batch-1",
            status="ignored",
            change_fields_json=json.dumps(["entity"]),
            current_entity="旧主体",
            new_entity="新主体",
        )
    )
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.get("/api/clients/contract-change-reviews")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["reviews"][0]["client_name"] == "Alpha"
    assert data["reviews"][0]["change_fields"] == ["fee_clause"]
    _clear_auth_override()


def test_approve_contract_change_review_updates_client(client, db_session):
    target = Client(name="Approve Me", business_type="广告", entity="旧主体", fee_clause="旧条款", payment_term="N30")
    db_session.add(target)
    db_session.flush()
    review = ClientContractChangeReview(
        client_name="Approve Me",
        source_type="feishu_sheet",
        source_token="sheet-2",
        sync_batch_id="batch-2",
        status="pending",
        change_fields_json=json.dumps(["fee_clause", "payment_term"]),
        current_fee_clause="旧条款",
        new_fee_clause="新条款",
        current_payment_term="N30",
        new_payment_term="N45",
        current_business_type="广告",
        new_business_type="广告",
        current_entity="旧主体",
        new_entity="旧主体",
    )
    db_session.add(review)
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.post(f"/api/clients/contract-change-reviews/{review.id}/approve")

    assert response.status_code == 200
    db_session.refresh(target)
    db_session.refresh(review)
    assert target.fee_clause == "新条款"
    assert target.payment_term == "N45"
    assert review.status == "approved"
    assert review.reviewed_by == FULL_PERMISSION_USER["username"]
    _clear_auth_override()


def test_ignore_contract_change_review_keeps_client_unchanged(client, db_session):
    target = Client(name="Ignore Me", entity="旧主体", fee_clause="旧条款")
    db_session.add(target)
    db_session.flush()
    review = ClientContractChangeReview(
        client_name="Ignore Me",
        source_type="feishu_sheet",
        source_token="sheet-3",
        sync_batch_id="batch-3",
        status="pending",
        change_fields_json=json.dumps(["entity", "fee_clause"]),
        current_entity="旧主体",
        new_entity="新主体",
        current_fee_clause="旧条款",
        new_fee_clause="新条款",
    )
    db_session.add(review)
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.post(f"/api/clients/contract-change-reviews/{review.id}/ignore")

    assert response.status_code == 200
    db_session.refresh(target)
    db_session.refresh(review)
    assert target.entity == "旧主体"
    assert target.fee_clause == "旧条款"
    assert review.status == "ignored"
    _clear_auth_override()


def test_batch_approve_contract_change_reviews_updates_multiple_clients(client, db_session):
    first = Client(name="Batch A", fee_clause="旧A")
    second = Client(name="Batch B", fee_clause="旧B")
    db_session.add_all([first, second])
    db_session.flush()
    review_one = ClientContractChangeReview(
        client_name="Batch A",
        source_type="feishu_sheet",
        source_token="sheet-4",
        sync_batch_id="batch-4",
        status="pending",
        change_fields_json=json.dumps(["fee_clause"]),
        current_fee_clause="旧A",
        new_fee_clause="新A",
    )
    review_two = ClientContractChangeReview(
        client_name="Batch B",
        source_type="feishu_sheet",
        source_token="sheet-4",
        sync_batch_id="batch-4",
        status="pending",
        change_fields_json=json.dumps(["fee_clause"]),
        current_fee_clause="旧B",
        new_fee_clause="新B",
    )
    db_session.add_all([review_one, review_two])
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.post(
        "/api/clients/contract-change-reviews/batch-approve",
        json={"review_ids": [review_one.id, review_two.id]},
    )

    assert response.status_code == 200
    db_session.refresh(first)
    db_session.refresh(second)
    db_session.refresh(review_one)
    db_session.refresh(review_two)
    assert response.json()["approved_count"] == 2
    assert first.fee_clause == "新A"
    assert second.fee_clause == "新B"
    assert review_one.status == "approved"
    assert review_two.status == "approved"
    _clear_auth_override()


def test_approve_contract_change_review_supports_fee_clause_override(client, db_session):
    target = Client(name="Approve Override", fee_clause="旧条款")
    db_session.add(target)
    db_session.flush()
    review = ClientContractChangeReview(
        client_name="Approve Override",
        source_type="feishu_sheet",
        source_token="sheet-override-1",
        sync_batch_id="batch-override-1",
        status="pending",
        change_fields_json=json.dumps(["fee_clause"]),
        current_fee_clause="旧条款",
        new_fee_clause="飞书新条款",
    )
    db_session.add(review)
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.post(
        f"/api/clients/contract-change-reviews/{review.id}/approve",
        json={"override_new_fee_clause": "人工修订条款"},
    )

    assert response.status_code == 200
    db_session.refresh(target)
    db_session.refresh(review)
    assert target.fee_clause == "人工修订条款"
    assert review.new_fee_clause == "人工修订条款"
    assert review.status == "approved"
    _clear_auth_override()


def test_batch_approve_contract_change_reviews_supports_fee_clause_overrides(client, db_session):
    first = Client(name="Batch Override A", fee_clause="旧A")
    second = Client(name="Batch Override B", fee_clause="旧B")
    db_session.add_all([first, second])
    db_session.flush()
    review_one = ClientContractChangeReview(
        client_name="Batch Override A",
        source_type="feishu_sheet",
        source_token="sheet-override-2",
        sync_batch_id="batch-override-2",
        status="pending",
        change_fields_json=json.dumps(["fee_clause"]),
        current_fee_clause="旧A",
        new_fee_clause="飞书A",
    )
    review_two = ClientContractChangeReview(
        client_name="Batch Override B",
        source_type="feishu_sheet",
        source_token="sheet-override-2",
        sync_batch_id="batch-override-2",
        status="pending",
        change_fields_json=json.dumps(["fee_clause"]),
        current_fee_clause="旧B",
        new_fee_clause="飞书B",
    )
    db_session.add_all([review_one, review_two])
    db_session.commit()

    _override_auth(FULL_PERMISSION_USER)
    response = client.post(
        "/api/clients/contract-change-reviews/batch-approve",
        json={
            "review_ids": [review_one.id, review_two.id],
            "override_new_fee_clause_by_review_id": {
                review_one.id: "人工A",
                review_two.id: "人工B",
            },
        },
    )

    assert response.status_code == 200
    db_session.refresh(first)
    db_session.refresh(second)
    db_session.refresh(review_one)
    db_session.refresh(review_two)
    assert first.fee_clause == "人工A"
    assert second.fee_clause == "人工B"
    assert review_one.new_fee_clause == "人工A"
    assert review_two.new_fee_clause == "人工B"
    assert review_one.status == "approved"
    assert review_two.status == "approved"
    _clear_auth_override()
