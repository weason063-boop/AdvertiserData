from api.database import upsert_client, get_all_clients, get_client_by_name, upsert_client_stats_batch, get_top_clients
import os

def test_orm():
    print("Testing ORM Migration...")
    
    # 1. Test Client Upsert
    client_id = upsert_client(name="Test Client", business_type="Ad", fee_clause="Fixed 1000")
    print(f"Upserted client, ID: {client_id}")
    
    # 2. Test Get Client
    client = get_client_by_name("Test Client")
    assert client is not None
    assert client['name'] == "Test Client"
    print("Client retrieval verified.")
    
    # 3. Test Stats Batch Upsert
    stats = [{"name": "Test Client", "consumption": 5000.0, "fee": 500.0}]
    upsert_client_stats_batch("2026-01", stats)
    print("Stats batch upserted.")
    
    # 4. Test Top Clients
    top = get_top_clients("2026-01")
    assert len(top) > 0
    assert top[0]['client_name'] == "Test Client"
    print("Top clients retrieval verified.")
    
    print("All ORM tests passed!")

if __name__ == "__main__":
    try:
        test_orm()
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
