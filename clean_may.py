
import sys
from api.database import SessionLocal
from api.models import ClientMonthlyStats, ClientMonthlyDetailStats, BillingHistory, ClientMonthlyNote

def main():
    db = SessionLocal()
    try:
        month = '2026-05'

        deleted_stats = db.query(ClientMonthlyStats).filter(ClientMonthlyStats.month == month).delete()
        deleted_details = db.query(ClientMonthlyDetailStats).filter(ClientMonthlyDetailStats.month == month).delete()
        deleted_history = db.query(BillingHistory).filter(BillingHistory.month == month).delete()
        deleted_notes = db.query(ClientMonthlyNote).filter(ClientMonthlyNote.month == month).delete()

        db.commit()

        print(f'Deleted {deleted_stats} from ClientMonthlyStats')
        print(f'Deleted {deleted_details} from ClientMonthlyDetailStats')
        print(f'Deleted {deleted_history} from BillingHistory')
        print(f'Deleted {deleted_notes} from ClientMonthlyNote')
    finally:
        db.close()

if __name__ == '__main__':
    main()

