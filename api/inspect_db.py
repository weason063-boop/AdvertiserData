
import sys
from pathlib import Path
import sqlite3

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from api.database import get_connection

def inspect_db():
    print("Inspecting Database...")
    conn = get_connection()
    
    # Check tables
    tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    print("Tables:", [t[0] for t in tables])
    
    # Check billing history
    try:
        rows = conn.execute("SELECT * FROM billing_history").fetchall()
        print(f"\nBilling History ({len(rows)}):")
        for r in rows:
            print(dict(r))
    except Exception as e:
        print(f"Error reading billing_history: {e}")
        
    # Check client stats
    try:
        rows = conn.execute("SELECT * FROM client_monthly_stats limit 10").fetchall()
        print(f"\nClient Monthly Stats ({len(rows)} sample):")
        for r in rows:
            print(dict(r))
    except Exception as e:
        print(f"Error reading client_monthly_stats: {e}")
        
    conn.close()

if __name__ == "__main__":
    inspect_db()
