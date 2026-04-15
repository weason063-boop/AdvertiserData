from api.database import (
    approve_contract_change_review,
    batch_approve_contract_change_reviews,
    get_all_clients,
    get_client,
    ignore_contract_change_review,
    list_contract_change_reviews,
    update_client,
    upsert_client,
)
from sqlalchemy.orm import Session

class ClientService:
    def list_clients(self, search: str = None, db: Session = None):
        return get_all_clients(search, db)

    def list_contract_change_reviews(self, search: str = None, db: Session = None):
        return list_contract_change_reviews(search, db)
    
    def get_client_detail(self, client_id: int, db: Session = None):
        return get_client(client_id, db)
        
    def update_client_clause(self, client_id: int, fee_clause: str, db: Session = None):
        return update_client(client_id, fee_clause, db)

    def add_client(self, name: str, business_type: str, fee_clause: str, db: Session = None):
        return upsert_client(name=name, business_type=business_type, fee_clause=fee_clause, db=db)

    def approve_contract_change_review(
        self,
        review_id: int,
        reviewer: str,
        db: Session = None,
        override_new_fee_clause: str | None = None,
    ):
        return approve_contract_change_review(review_id, reviewer, db, override_new_fee_clause)

    def ignore_contract_change_review(self, review_id: int, reviewer: str, db: Session = None):
        return ignore_contract_change_review(review_id, reviewer, db)

    def batch_approve_contract_change_reviews(
        self,
        review_ids: list[int],
        reviewer: str,
        db: Session = None,
        override_new_fee_clause_by_review_id: dict[int, str] | None = None,
    ):
        return batch_approve_contract_change_reviews(
            review_ids,
            reviewer,
            db,
            override_new_fee_clause_by_review_id,
        )
