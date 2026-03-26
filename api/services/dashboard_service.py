from datetime import datetime
from dateutil.relativedelta import relativedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Dict, List
import re

from api.database import get_top_clients, SessionLocal
from api.models import BillingHistory, ClientMonthlyStats

class DashboardService:
    _MONTH_PATTERN = re.compile(r"^(20\d{2})-(0[1-9]|1[0-2])$")

    def _is_valid_month(self, month: str | None) -> bool:
        return bool(month and self._MONTH_PATTERN.match(month))

    def _get_previous_month(self, month: str) -> str | None:
        """Return previous month in YYYY-MM format."""
        try:
            target = datetime.strptime(month, "%Y-%m")
            return (target - relativedelta(months=1)).strftime("%Y-%m")
        except Exception:
            return None

    def _get_available_months(self, db: Session) -> List[str]:
        rows = db.query(ClientMonthlyStats.month).distinct().all()
        months = [r[0] for r in rows if r and self._is_valid_month(r[0])]
        months.sort()
        return months

    def _find_previous_available_month(self, month: str, db: Session) -> str | None:
        months = self._get_available_months(db)
        earlier = [m for m in months if m < month]
        return earlier[-1] if earlier else None

    def _month_to_custom_quarter(self, month: str) -> tuple[str, int]:
        """
        Custom quarter rule:
        Q1: 3-5月, Q2: 6-8月, Q3: 9-11月, Q4: 12月-次年2月
        """
        dt = datetime.strptime(month, "%Y-%m")
        m = dt.month
        y = dt.year
        if m in (3, 4, 5):
            return str(y), 1
        if m in (6, 7, 8):
            return str(y), 2
        if m in (9, 10, 11):
            return str(y), 3
        if m == 12:
            return str(y), 4
        return str(y - 1), 4

    def _quarter_key(self, year: str, quarter: int) -> str:
        return f"{year}-Q{quarter}"

    def _quarter_of_month(self, month: str) -> str:
        year, q = self._month_to_custom_quarter(month)
        return self._quarter_key(year, q)

    def _get_previous_quarter(self, quarter: str) -> str | None:
        try:
            year_text, q_text = quarter.split("-Q")
            year = int(year_text)
            q = int(q_text)
        except Exception:
            return None
        if q > 1:
            return f"{year}-Q{q - 1}"
        return f"{year - 1}-Q4"

    def _get_yoy_quarter(self, quarter: str) -> str | None:
        parsed = re.match(r"^(\d{4})-Q([1-4])$", quarter or "")
        if not parsed:
            return None
        year = int(parsed.group(1))
        q = int(parsed.group(2))
        return f"{year - 1}-Q{q}"

    def _get_yoy_month(self, month: str) -> str | None:
        if not self._is_valid_month(month):
            return None
        year_text, month_text = month.split("-")
        return f"{int(year_text) - 1}-{month_text}"

    def _normalize_month_compare_mode(self, compare_prev: bool, compare_mode: str | None) -> str:
        normalized = (compare_mode or "").strip().lower()
        if not normalized:
            normalized = "mom" if compare_prev else "none"
        if normalized not in {"none", "mom", "yoy", "dual"}:
            normalized = "none"
        return normalized

    def _normalize_quarter_compare_mode(self, compare_prev: bool, compare_mode: str | None) -> str:
        normalized = (compare_mode or "").strip().lower()
        if not normalized:
            normalized = "qoq" if compare_prev else "none"
        if normalized not in {"none", "qoq", "yoy", "dual"}:
            normalized = "none"
        return normalized

    def _build_metrics_map(self, rows: List[dict]) -> Dict[str, Dict[str, float]]:
        return {
            row["client_name"]: {
                "consumption": float(row.get("consumption") or 0.0),
                "service_fee": float(row.get("service_fee") or 0.0),
            }
            for row in rows
        }

    def _build_rank_map(self, rows: List[dict]) -> Dict[str, int]:
        return {
            row["client_name"]: idx
            for idx, row in enumerate(rows, start=1)
        }

    def _get_quarter_months_map(self, db: Session) -> Dict[str, List[str]]:
        month_map: Dict[str, List[str]] = {}
        for month in self._get_available_months(db):
            key = self._quarter_of_month(month)
            month_map.setdefault(key, []).append(month)
        return month_map

    def _aggregate_top_clients_by_months(self, months: List[str], limit: int, db: Session):
        if not months:
            return []
        rows = db.query(
            ClientMonthlyStats.client_name,
            func.sum(ClientMonthlyStats.consumption).label("consumption"),
            func.sum(ClientMonthlyStats.service_fee).label("service_fee"),
        ).filter(
            ClientMonthlyStats.month.in_(months)
        ).group_by(
            ClientMonthlyStats.client_name
        ).order_by(
            desc(func.sum(ClientMonthlyStats.consumption))
        ).limit(limit).all()

        data = [
            {
                "client_name": row.client_name,
                "consumption": float(row.consumption or 0.0),
                "service_fee": float(row.service_fee or 0.0),
            }
            for row in rows
        ]
        return data

    def get_main_stats(self, db: Session = None):
        """
        Calculate and return main dashboard statistics (Consumption, Fee, MoM, YoY).
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            rows = db.query(
                BillingHistory.month,
                BillingHistory.total_consumption,
                BillingHistory.total_service_fee,
            ).order_by(BillingHistory.month).all()
            history = [
                {
                    "month": row.month,
                    "total_consumption": float(row.total_consumption or 0.0),
                    "total_service_fee": float(row.total_service_fee or 0.0),
                }
                for row in rows
                if self._is_valid_month(row.month)
            ]
            
            if not history:
                return {"stats": None, "trend": [], "top_clients": []}
            
            current = history[-1]
            prev = history[-2] if len(history) > 1 else None
            history_lookup = {item["month"]: item for item in history}
            
            # Find last year's same month
            try:
                curr_date = datetime.strptime(current['month'], "%Y-%m")
                last_year_month = f"{curr_date.year - 1}-{curr_date.month:02d}"
                last_year = history_lookup.get(last_year_month)
            except Exception:
                last_year = None
                
            def calc_change(curr, old):
                if not old or old == 0: return 0.0
                return ((curr - old) / old) * 100

            stats = {
                "consumption": current['total_consumption'],
                "fee": current['total_service_fee'],
                "month": current['month'],
                # MoM
                "consumption_mom": calc_change(current['total_consumption'], prev['total_consumption']) if prev else 0,
                "fee_mom": calc_change(current['total_service_fee'], prev['total_service_fee']) if prev else 0,
                # YoY
                "consumption_yoy": calc_change(current['total_consumption'], last_year['total_consumption']) if last_year else 0,
                "fee_yoy": calc_change(current['total_service_fee'], last_year['total_service_fee']) if last_year else 0,
            }
            
            # Get Top 10 Clients for current month
            top_clients = get_top_clients(current['month'], limit=10, db=db)
            
            return {
                "stats": stats,
                "trend": history,
                "top_clients": top_clients
            }
        finally:
            if should_close:
                db.close()
    
    def get_client_trend(self, client_name: str, db: Session = None) -> Dict:
        """获取指定客户的月度消耗趋势"""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            # Get latest month from DB
            latest_month_row = db.query(ClientMonthlyStats.month).order_by(desc(ClientMonthlyStats.month)).first()
            if not latest_month_row:
                return {"client_name": client_name, "data": [], "summary": {"total_consumption": 0, "avg_monthly": 0, "peak_month": None, "peak_value": 0}}
            
            latest_month = latest_month_row[0]
            latest_date = datetime.strptime(latest_month, '%Y-%m')
            
            # Generate 12-month range
            months = [(latest_date - relativedelta(months=i)).strftime('%Y-%m') for i in range(11, -1, -1)]
            
            # Query only the visible 12-month window to avoid scanning full history.
            earliest_month = months[0]
            records = db.query(
                ClientMonthlyStats.month,
                ClientMonthlyStats.consumption,
                ClientMonthlyStats.service_fee,
            ).filter(
                ClientMonthlyStats.client_name == client_name,
                ClientMonthlyStats.month >= earliest_month,
            ).order_by(ClientMonthlyStats.month).all()
            
            data_lookup = {r.month: {"month": r.month, "consumption": r.consumption, "service_fee": r.service_fee} for r in records}
            
            complete_data = []
            for m in months:
                complete_data.append(data_lookup.get(m, {"month": m, "consumption": 0, "service_fee": 0}))
            
            if not records:
                return {"client_name": client_name, "data": complete_data, "summary": {"total_consumption": 0, "avg_monthly": 0, "peak_month": None, "peak_value": 0}}
            
            # Keep summary aligned with the visible 12-month chart window so
            # stale or malformed historical rows do not skew the dashboard card.
            window_records = [item for item in complete_data if item["consumption"] > 0]
            total_consumption = sum(item["consumption"] for item in window_records)
            avg_monthly = total_consumption / len(window_records) if window_records else 0
            peak_record = max(window_records, key=lambda item: item["consumption"]) if window_records else None
            
            return {
                "client_name": client_name,
                "data": complete_data,
                "summary": {
                    "total_consumption": total_consumption,
                    "avg_monthly": round(avg_monthly, 2),
                    "peak_month": peak_record["month"] if peak_record else None,
                    "peak_value": peak_record["consumption"] if peak_record else 0
                }
            }
        finally:
            if should_close:
                db.close()

    def get_insights(self, db: Session = None) -> Dict:
        """获取仪表盘洞察数据（异常、流失、增长、分层）"""
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            # 1. Get latest month
            latest_month = db.query(func.max(ClientMonthlyStats.month)).scalar()
            if not latest_month:
                return {}
            
            # 2. Limit analysis to recent months to avoid full-table scans.
            latest_date = datetime.strptime(latest_month, "%Y-%m")
            analysis_window_start = (latest_date - relativedelta(months=17)).strftime("%Y-%m")
            records = db.query(
                ClientMonthlyStats.client_name,
                ClientMonthlyStats.month,
                ClientMonthlyStats.consumption,
            ).filter(
                ClientMonthlyStats.month >= analysis_window_start
            ).order_by(desc(ClientMonthlyStats.month)).all()
            
            client_history = {}
            for r in records:
                if r.client_name not in client_history:
                    client_history[r.client_name] = []
                client_history[r.client_name].append(r)
                
            anomalies = []
            churn_risk = []
            growth_stars = []
            
            current_month_data = [r for r in records if r.month == latest_month]
            current_month_data.sort(key=lambda x: x.consumption, reverse=True)
            total_revenue = sum(x.consumption for x in current_month_data)
            
            for client, history in client_history.items():
                if not history: continue
                latest_record = history[0]
                
                if latest_record.month != latest_month:
                    # Potential Churn
                    prev_month = [r for r in history if r.month < latest_month]
                    if prev_month and prev_month[0].consumption > 10000:
                        churn_risk.append({"client": client, "trend": "dropped_to_zero", "consecutive_months": 1})
                    continue
                    
                current_val = latest_record.consumption
                
                # Anomaly Detection
                prev_3_months = history[1:4]
                if prev_3_months:
                    avg_prev = sum(r.consumption for r in prev_3_months) / len(prev_3_months)
                    if avg_prev > 1000:
                        change_pct = ((current_val - avg_prev) / avg_prev) * 100
                        if change_pct > 50 and current_val > 5000:
                            anomalies.append({"client": client, "type": "surge", "value": current_val, "change_pct": round(change_pct, 1)})
                        elif change_pct < -50:
                            anomalies.append({"client": client, "type": "drop", "value": current_val, "change_pct": round(change_pct, 1)})
                            
                # Churn Risk (Declining)
                if len(history) >= 4:
                    m1, m2, m3 = history[0].consumption, history[1].consumption, history[2].consumption
                    if m3 > 10000 and m3 > m2 > m1 and m1 < (m3 * 0.7):
                        recent_vals = [{"month": r.month, "consumption": r.consumption} for r in history[:6]]
                        recent_vals.reverse()
                        churn_risk.append({"client": client, "trend": "declining", "consecutive_months": 3, "recent_values": recent_vals})
                        
                # Growth Stars
                if len(history) >= 2:
                    prev_val = history[1].consumption
                    growth = current_val - prev_val
                    if growth > 2000 and current_val > prev_val * 1.1:
                        growth_stars.append({"client": client, "growth_amount": growth, "rank_change": 0})

            # Segmentation
            running_rev = 0
            whales, core, long_tail = [], [], []
            for r in current_month_data:
                start_pct = running_rev / total_revenue if total_revenue > 0 else 0
                running_rev += r.consumption
                if start_pct < 0.5: whales.append(r)
                elif start_pct < 0.8: core.append(r)
                else: long_tail.append(r)
                
            is_whale_client = {w.client_name for w in whales}
            growth_stars = [g for g in growth_stars if g['client'] not in is_whale_client]
            
            anomalies.sort(key=lambda x: abs(x['change_pct']), reverse=True)
            growth_stars.sort(key=lambda x: x['growth_amount'], reverse=True)
            
            segmentation = {
                "whales": {
                    "count": len(whales), 
                    "value": sum(x.consumption for x in whales), 
                    "pct": round(sum(x.consumption for x in whales)/total_revenue*100, 1) if total_revenue else 0,
                    "top_clients": [{"client": w.client_name, "value": w.consumption} for w in whales[:5]]
                },
                "core": {"count": len(core), "value": sum(x.consumption for x in core), "pct": round(sum(x.consumption for x in core)/total_revenue*100, 1) if total_revenue else 0},
                "long_tail": {"count": len(long_tail), "value": sum(x.consumption for x in long_tail), "pct": round(sum(x.consumption for x in long_tail)/total_revenue*100, 1) if total_revenue else 0}
            }
            
            return {
                "metrics": {
                    "anomalies": anomalies[:5],
                    "churn_risk": churn_risk[:5],
                    "growth_stars": growth_stars[:5]
                },
                "segmentation": segmentation
            }
        finally:
            if should_close:
                db.close()
    
    def get_month_top_clients(
        self,
        month: str,
        limit: int,
        db: Session = None,
        compare_prev: bool = False,
        compare_mode: str | None = None,
    ):
        """
        Get top N clients for a specific month.
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            clients = get_top_clients(month, limit, db)
            normalized_compare_mode = self._normalize_month_compare_mode(compare_prev, compare_mode)
            response = {
                "month": month,
                "clients": clients,
                "compare_mode": normalized_compare_mode,
            }

            if normalized_compare_mode == "none":
                return response

            prev_month = self._get_previous_month(month)
            if prev_month:
                has_prev_rows = db.query(ClientMonthlyStats.id).filter(
                    ClientMonthlyStats.month == prev_month
                ).first()
                if not has_prev_rows:
                    prev_month = self._find_previous_available_month(month, db)
            else:
                prev_month = self._find_previous_available_month(month, db)
            response["prev_month"] = prev_month

            yoy_month = self._get_yoy_month(month)
            if yoy_month:
                has_yoy_rows = db.query(ClientMonthlyStats.id).filter(
                    ClientMonthlyStats.month == yoy_month
                ).first()
                if not has_yoy_rows:
                    yoy_month = None
            response["yoy_month"] = yoy_month

            prev_rows = get_top_clients(prev_month, 100000, db) if prev_month else []
            yoy_rows = get_top_clients(yoy_month, 100000, db) if yoy_month else []
            prev_metrics_map = self._build_metrics_map(prev_rows)
            prev_rank_map = self._build_rank_map(prev_rows)
            yoy_metrics_map = self._build_metrics_map(yoy_rows)
            yoy_rank_map = self._build_rank_map(yoy_rows)

            enriched_clients = []
            for curr_rank, item in enumerate(clients, start=1):
                client_name = item["client_name"]
                curr_consumption = float(item.get("consumption") or 0.0)
                curr_service_fee = float(item.get("service_fee") or 0.0)
                prev_values = prev_metrics_map.get(client_name)
                prev_rank = prev_rank_map.get(client_name)

                prev_consumption = prev_values["consumption"] if prev_values else None
                prev_service_fee = prev_values["service_fee"] if prev_values else None
                consumption_delta = curr_consumption - prev_consumption if prev_consumption is not None else None
                fee_delta = curr_service_fee - prev_service_fee if prev_service_fee is not None else None
                rank_change = (prev_rank - curr_rank) if prev_rank is not None else None

                yoy_values = yoy_metrics_map.get(client_name)
                yoy_rank = yoy_rank_map.get(client_name)
                yoy_consumption = yoy_values["consumption"] if yoy_values else None
                yoy_service_fee = yoy_values["service_fee"] if yoy_values else None
                yoy_delta = curr_consumption - yoy_consumption if yoy_consumption is not None else None
                yoy_fee_delta = curr_service_fee - yoy_service_fee if yoy_service_fee is not None else None

                enriched_clients.append({
                    **item,
                    "rank": curr_rank,
                    "prev_consumption": prev_consumption,
                    "prev_service_fee": prev_service_fee,
                    "consumption_delta": consumption_delta,
                    "fee_delta": fee_delta,
                    "rank_change": rank_change,
                    "prev_month_consumption": prev_consumption,
                    "prev_month_service_fee": prev_service_fee,
                    "prev_month_rank": prev_rank,
                    "yoy_consumption": yoy_consumption,
                    "yoy_service_fee": yoy_service_fee,
                    "yoy_rank": yoy_rank,
                    "mom_delta": consumption_delta,
                    "mom_fee_delta": fee_delta,
                    "mom_rank_change": rank_change,
                    "yoy_delta": yoy_delta,
                    "yoy_fee_delta": yoy_fee_delta,
                    "yoy_rank_change": (yoy_rank - curr_rank) if yoy_rank is not None else None,
                })

            response["clients"] = enriched_clients
            return response
        finally:
            if should_close:
                db.close()

    def get_quarter_top_clients(
        self,
        quarter: str,
        limit: int,
        db: Session = None,
        compare_prev: bool = False,
        compare_mode: str | None = None,
    ):
        """
        Get top N clients for a custom quarter.
        quarter format: YYYY-QN
        """
        should_close = False
        if db is None:
            db = SessionLocal()
            should_close = True
        try:
            quarter_months_map = self._get_quarter_months_map(db)
            current_months = quarter_months_map.get(quarter, [])
            clients = self._aggregate_top_clients_by_months(current_months, limit, db)
            normalized_compare_mode = self._normalize_quarter_compare_mode(compare_prev, compare_mode)
            response = {
                "quarter": quarter,
                "months": current_months,
                "clients": clients,
                "compare_mode": normalized_compare_mode,
            }

            if normalized_compare_mode == "none":
                return response

            prev_quarter = self._get_previous_quarter(quarter)
            if prev_quarter and not quarter_months_map.get(prev_quarter):
                keys = sorted(quarter_months_map.keys())
                earlier = [k for k in keys if k < quarter]
                prev_quarter = earlier[-1] if earlier else None
            response["prev_quarter"] = prev_quarter

            yoy_quarter = self._get_yoy_quarter(quarter)
            if yoy_quarter and not quarter_months_map.get(yoy_quarter):
                yoy_quarter = None
            response["yoy_quarter"] = yoy_quarter

            prev_months = quarter_months_map.get(prev_quarter, []) if prev_quarter else []
            yoy_months = quarter_months_map.get(yoy_quarter, []) if yoy_quarter else []
            prev_rows = self._aggregate_top_clients_by_months(prev_months, 100000, db)
            yoy_rows = self._aggregate_top_clients_by_months(yoy_months, 100000, db)
            prev_metrics_map = self._build_metrics_map(prev_rows)
            prev_rank_map = self._build_rank_map(prev_rows)
            yoy_metrics_map = self._build_metrics_map(yoy_rows)
            yoy_rank_map = self._build_rank_map(yoy_rows)

            enriched_clients = []
            for curr_rank, item in enumerate(clients, start=1):
                client_name = item["client_name"]
                curr_consumption = float(item.get("consumption") or 0.0)
                curr_service_fee = float(item.get("service_fee") or 0.0)

                prev_values = prev_metrics_map.get(client_name)
                prev_rank = prev_rank_map.get(client_name)
                prev_consumption = prev_values["consumption"] if prev_values else None
                prev_service_fee = prev_values["service_fee"] if prev_values else None

                yoy_values = yoy_metrics_map.get(client_name)
                yoy_rank = yoy_rank_map.get(client_name)
                yoy_consumption = yoy_values["consumption"] if yoy_values else None
                yoy_service_fee = yoy_values["service_fee"] if yoy_values else None

                qoq_delta = (curr_consumption - prev_consumption) if prev_consumption is not None else None
                qoq_fee_delta = (curr_service_fee - prev_service_fee) if prev_service_fee is not None else None
                yoy_delta = (curr_consumption - yoy_consumption) if yoy_consumption is not None else None
                yoy_fee_delta = (curr_service_fee - yoy_service_fee) if yoy_service_fee is not None else None

                enriched_clients.append({
                    **item,
                    "rank": curr_rank,
                    "prev_quarter_consumption": prev_consumption,
                    "prev_quarter_service_fee": prev_service_fee,
                    "prev_quarter_rank": prev_rank,
                    "yoy_consumption": yoy_consumption,
                    "yoy_service_fee": yoy_service_fee,
                    "yoy_rank": yoy_rank,
                    "qoq_delta": qoq_delta,
                    "qoq_fee_delta": qoq_fee_delta,
                    "qoq_rank_change": (prev_rank - curr_rank) if prev_rank is not None else None,
                    "yoy_delta": yoy_delta,
                    "yoy_fee_delta": yoy_fee_delta,
                    "yoy_rank_change": (yoy_rank - curr_rank) if yoy_rank is not None else None,
                    "prev_consumption": prev_consumption,
                    "prev_service_fee": prev_service_fee,
                    "consumption_delta": qoq_delta,
                    "fee_delta": qoq_fee_delta,
                    "rank_change": (prev_rank - curr_rank) if prev_rank is not None else None,
                })

            response["clients"] = enriched_clients
            return response
        finally:
            if should_close:
                db.close()
