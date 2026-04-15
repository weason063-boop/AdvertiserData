import json

from api.migrate import migrate_feishu_contract_lines
from api.models import Client, ClientContractChangeReview


def test_migrate_feishu_contract_lines_creates_pending_review_for_existing_client(db_session, monkeypatch):
    monkeypatch.setattr("api.migrate.SessionLocal", lambda: db_session)
    db_session.add(
        Client(
            name="Alpha",
            business_type="广告",
            department="华东",
            entity="旧主体",
            fee_clause="旧条款",
            payment_term="N30",
        )
    )
    db_session.commit()

    stats = migrate_feishu_contract_lines(
        [
            {
                "name": "Alpha",
                "business_type": "广告",
                "department": "华东",
                "entity": "新主体",
                "fee_clause": "新条款",
                "payment_term": "N45",
                "_source_row_index": 2,
            }
        ],
        source_token="sheet-alpha",
        source_type="feishu_sheet",
    )

    client = db_session.query(Client).filter(Client.name == "Alpha").first()
    review = db_session.query(ClientContractChangeReview).filter(
        ClientContractChangeReview.client_name == "Alpha",
        ClientContractChangeReview.status == "pending",
    ).first()

    assert stats["line_count"] == 1
    assert stats["client_count"] == 1
    assert stats["new_client_count"] == 0
    assert stats["pending_count"] == 1
    assert stats["unchanged_count"] == 0
    assert client is not None
    assert client.entity == "旧主体"
    assert client.fee_clause == "旧条款"
    assert client.payment_term == "N30"
    assert review is not None
    assert json.loads(review.change_fields_json) == ["entity", "fee_clause", "payment_term"]
    assert review.current_fee_clause == "旧条款"
    assert review.new_fee_clause == "新条款"


def test_migrate_feishu_contract_lines_auto_adds_new_clients(db_session, monkeypatch):
    monkeypatch.setattr("api.migrate.SessionLocal", lambda: db_session)

    stats = migrate_feishu_contract_lines(
        [
            {
                "name": "Brand New",
                "business_type": "广告",
                "department": "华北",
                "entity": "新主体",
                "fee_clause": "5%",
                "payment_term": "N15",
                "_source_row_index": 3,
            }
        ],
        source_token="sheet-new",
        source_type="feishu_sheet",
    )

    client = db_session.query(Client).filter(Client.name == "Brand New").first()
    review_count = db_session.query(ClientContractChangeReview).count()

    assert stats["new_client_count"] == 1
    assert stats["pending_count"] == 0
    assert stats["new_clients"] == ["Brand New"]
    assert client is not None
    assert client.fee_clause == "5%"
    assert review_count == 0


def test_migrate_feishu_contract_lines_reuses_existing_pending_review(db_session, monkeypatch):
    monkeypatch.setattr("api.migrate.SessionLocal", lambda: db_session)
    db_session.add(
        Client(
            name="Reuse Pending",
            business_type="广告",
            entity="旧主体",
            fee_clause="旧条款",
            payment_term="N30",
        )
    )
    db_session.commit()

    first_stats = migrate_feishu_contract_lines(
        [
            {
                "name": "Reuse Pending",
                "business_type": "广告",
                "entity": "新主体A",
                "fee_clause": "新条款A",
                "payment_term": "N45",
                "_source_row_index": 4,
            }
        ],
        source_token="sheet-reuse",
        source_type="feishu_sheet",
    )

    second_stats = migrate_feishu_contract_lines(
        [
            {
                "name": "Reuse Pending",
                "business_type": "广告",
                "entity": "新主体B",
                "fee_clause": "新条款B",
                "payment_term": "N60",
                "_source_row_index": 4,
            }
        ],
        source_token="sheet-reuse",
        source_type="feishu_sheet",
    )

    pending_reviews = db_session.query(ClientContractChangeReview).filter(
        ClientContractChangeReview.client_name == "Reuse Pending",
        ClientContractChangeReview.status == "pending",
    ).all()

    assert first_stats["pending_count"] == 1
    assert second_stats["pending_count"] == 1
    assert len(pending_reviews) == 1
    assert pending_reviews[0].new_entity == "新主体B"
    assert pending_reviews[0].new_fee_clause == "新条款B"
    assert pending_reviews[0].new_payment_term == "N60"
