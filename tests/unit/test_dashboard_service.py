from api.database import upsert_client_stats_batch
from api.services.dashboard_service import DashboardService


class TestDashboardService:
    def test_client_trend_summary_uses_visible_12_month_window(self, db_session):
        upsert_client_stats_batch(
            "1970-01",
            [{"name": "Test Client", "consumption": 999999, "fee": 0}],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2025-12",
            [{"name": "Test Client", "consumption": 200, "fee": 20}],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-01",
            [{"name": "Test Client", "consumption": 500, "fee": 50}],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-02",
            [{"name": "Test Client", "consumption": 300, "fee": 30}],
            db=db_session,
        )

        result = DashboardService().get_client_trend("Test Client", db=db_session)

        assert len(result["data"]) == 12
        assert result["summary"]["total_consumption"] == 1000
        assert result["summary"]["avg_monthly"] == 333.33
        assert result["summary"]["peak_month"] == "2026-01"
        assert result["summary"]["peak_value"] == 500

    def test_quarter_top_clients_supports_dual_compare_mode(self, db_session):
        upsert_client_stats_batch(
            "2025-03",
            [
                {"name": "Alpha", "consumption": 50, "fee": 5},
                {"name": "Beta", "consumption": 30, "fee": 3},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2025-04",
            [
                {"name": "Alpha", "consumption": 60, "fee": 6},
                {"name": "Beta", "consumption": 20, "fee": 2},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2025-05",
            [
                {"name": "Alpha", "consumption": 70, "fee": 7},
                {"name": "Beta", "consumption": 10, "fee": 1},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2025-12",
            [
                {"name": "Alpha", "consumption": 40, "fee": 4},
                {"name": "Beta", "consumption": 50, "fee": 5},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-01",
            [
                {"name": "Alpha", "consumption": 40, "fee": 4},
                {"name": "Beta", "consumption": 50, "fee": 5},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-02",
            [
                {"name": "Alpha", "consumption": 40, "fee": 4},
                {"name": "Beta", "consumption": 50, "fee": 5},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-03",
            [
                {"name": "Alpha", "consumption": 100, "fee": 10},
                {"name": "Beta", "consumption": 80, "fee": 8},
                {"name": "Gamma", "consumption": 20, "fee": 2},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-04",
            [
                {"name": "Alpha", "consumption": 110, "fee": 11},
                {"name": "Beta", "consumption": 70, "fee": 7},
                {"name": "Gamma", "consumption": 30, "fee": 3},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-05",
            [
                {"name": "Alpha", "consumption": 90, "fee": 9},
                {"name": "Beta", "consumption": 90, "fee": 9},
                {"name": "Gamma", "consumption": 40, "fee": 4},
            ],
            db=db_session,
        )

        result = DashboardService().get_quarter_top_clients(
            "2026-Q1",
            10,
            db=db_session,
            compare_mode="dual",
        )

        assert result["compare_mode"] == "dual"
        assert result["prev_quarter"] == "2025-Q4"
        assert result["yoy_quarter"] == "2025-Q1"

        alpha = next(item for item in result["clients"] if item["client_name"] == "Alpha")
        beta = next(item for item in result["clients"] if item["client_name"] == "Beta")

        assert alpha["consumption"] == 300.0
        assert alpha["prev_quarter_consumption"] == 120.0
        assert alpha["yoy_consumption"] == 180.0
        assert alpha["qoq_delta"] == 180.0
        assert alpha["yoy_delta"] == 120.0
        assert alpha["qoq_rank_change"] == 1
        assert alpha["yoy_rank_change"] == 0

        assert beta["consumption"] == 240.0
        assert beta["prev_quarter_consumption"] == 150.0
        assert beta["yoy_consumption"] == 60.0
        assert beta["qoq_rank_change"] == -1
        assert beta["yoy_rank_change"] == 0

    def test_month_top_clients_supports_dual_compare_mode(self, db_session):
        upsert_client_stats_batch(
            "2025-02",
            [
                {"name": "Alpha", "consumption": 120, "fee": 12},
                {"name": "Beta", "consumption": 20, "fee": 2},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-01",
            [
                {"name": "Alpha", "consumption": 90, "fee": 9},
                {"name": "Beta", "consumption": 110, "fee": 11},
                {"name": "Gamma", "consumption": 40, "fee": 4},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-02",
            [
                {"name": "Alpha", "consumption": 150, "fee": 15},
                {"name": "Beta", "consumption": 80, "fee": 8},
                {"name": "Gamma", "consumption": 60, "fee": 6},
            ],
            db=db_session,
        )

        result = DashboardService().get_month_top_clients(
            "2026-02",
            10,
            db=db_session,
            compare_mode="dual",
        )

        assert result["compare_mode"] == "dual"
        assert result["prev_month"] == "2026-01"
        assert result["yoy_month"] == "2025-02"

        alpha = next(item for item in result["clients"] if item["client_name"] == "Alpha")
        gamma = next(item for item in result["clients"] if item["client_name"] == "Gamma")

        assert alpha["prev_month_consumption"] == 90.0
        assert alpha["yoy_consumption"] == 120.0
        assert alpha["mom_delta"] == 60.0
        assert alpha["yoy_delta"] == 30.0
        assert alpha["mom_rank_change"] == 1
        assert alpha["yoy_rank_change"] == 0

        assert gamma["prev_month_consumption"] == 40.0
        assert gamma["yoy_consumption"] is None
        assert gamma["mom_delta"] == 20.0
        assert gamma["yoy_delta"] is None
