from api.database import get_all_clients, get_client, update_client, upsert_client
from sqlalchemy.orm import Session

class ClientService:
    def list_clients(self, search: str = None, db: Session = None):
        return get_all_clients(search, db)
    
    def get_client_detail(self, client_id: int, db: Session = None):
        return get_client(client_id, db)
        
    def update_client_clause(self, client_id: int, fee_clause: str, db: Session = None):
        return update_client(client_id, fee_clause, db)

    def add_client(self, name: str, business_type: str, fee_clause: str, db: Session = None):
        return upsert_client(name=name, business_type=business_type, fee_clause=fee_clause, db=db)
