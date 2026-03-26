
import sys
from pathlib import Path
import sqlite3

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from api.database import get_connection

def clean_feb_data():
    print("Cleaning Feb 2026 data...")
    conn = get_connection()
    
    # Delete from billing_history
    conn.execute("DELETE FROM billing_history WHERE month = '2026-02'")
    
    # Delete from client_monthly_stats
    conn.execute("DELETE FROM client_monthly_stats WHERE month = '2026-02'")
    
    conn.commit()
    conn.close()
    print("Done. Please re-run inspect_db to verify.")

if __name__ == "__main__":
    clean_feb_data()
