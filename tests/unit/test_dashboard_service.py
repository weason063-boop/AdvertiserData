import pandas as pd

from api.database import upsert_client_detail_stats_batch, upsert_client_stats_batch
from api.models import Client
from api.services.calculation_service import CalculationService
from api.services.dashboard_service import DashboardService


class TestDashboardService:
    def test_get_latest_month_clients_returns_latest_month_sorted_by_consumption(self, db_session):
        upsert_client_stats_batch(
            "2026-01",
            [
                {"name": "Alpha", "consumption": 90, "fee": 9},
                {"name": "Beta", "consumption": 110, "fee": 11},
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-02",
            [
                {"name": "Alpha", "consumption": 150, "fee": 15},
                {"name": "Gamma", "consumption": 80, "fee": 8},
                {"name": "Beta", "consumption": 120, "fee": 12},
            ],
            db=db_session,
        )

        result = DashboardService().get_latest_month_clients(db=db_session)

        assert result["latest_month"] == "2026-02"
        assert [item["client_name"] for item in result["rows"]] == ["Alpha", "Beta", "Gamma"]
        assert result["rows"][0]["consumption"] == 150.0
        assert result["rows"][1]["service_fee"] == 12.0
        assert result["rows"][0]["month"] == "2026-02"
        assert result["rows"][0]["entity"] is None
        assert result["rows"][0]["owner"] is None
        assert result["rows"][0]["bill_amount"] == 165.0
        assert result["rows"][0]["note"] is None

    def test_get_client_history_returns_profile_and_desc_rows(self, db_session):
        db_session.add(
            Client(
                name="Alpha",
                business_type="Agency",
                department="North",
                entity="Entity-A",
                fee_clause="5%",
            )
        )
        db_session.commit()

        upsert_client_stats_batch(
            "2025-12",
            [{"name": "Alpha", "consumption": 100, "fee": 10}],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-01",
            [{"name": "Alpha", "consumption": 110, "fee": 11}],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2026-02",
            [{"name": "Alpha", "consumption": 120, "fee": 12}],
            db=db_session,
        )

        result = DashboardService().get_client_history("Alpha", db=db_session)

        assert result["profile"]["client_name"] == "Alpha"
        assert result["profile"]["business_type"] == "Agency"
        assert [item["month"] for item in result["rows"]] == ["2026-02", "2026-01", "2025-12"]
        assert result["summary"]["latest_month"] == "2026-02"
        assert result["summary"]["first_month"] == "2025-12"
        assert result["summary"]["total_consumption"] == 330.0
        assert result["summary"]["total_service_fee"] == 33.0

    def test_get_client_history_allows_missing_profile(self, db_session):
        upsert_client_stats_batch(
            "2026-02",
            [{"name": "Missing Profile", "consumption": 88, "fee": 8}],
            db=db_session,
        )

        result = DashboardService().get_client_history("Missing Profile", db=db_session)

        assert result["profile"]["client_name"] == "Missing Profile"
        assert result["profile"]["business_type"] is None
        assert result["summary"]["latest_month"] == "2026-02"
        assert result["rows"][0]["consumption"] == 88.0

    def test_get_latest_month_clients_returns_detail_metrics_when_available(self, db_session):
        db_session.add(
            Client(
                name="Alpha",
                business_type="Agency",
                department="Nora",
                entity="Entity-A",
                fee_clause="5%",
            )
        )
        db_session.commit()

        upsert_client_detail_stats_batch(
            "2026-02",
            [
                {
                    "name": "Alpha",
                    "bill_type": "预付",
                    "service_type": "代投",
                    "flow_consumption": 90,
                    "managed_consumption": 60,
                    "net_consumption": 145,
                    "service_fee": 8,
                    "fixed_service_fee": 2,
                    "coupon": -5,
                    "dst": 3,
                    "total": 155,
                },
                {
                    "name": "Beta",
                    "bill_type": "后付",
                    "service_type": "直客",
                    "flow_consumption": 40,
                    "managed_consumption": 20,
                    "net_consumption": 58,
                    "service_fee": 3,
                    "fixed_service_fee": 1,
                    "coupon": 0,
                    "dst": 1,
                    "total": 62,
                },
            ],
            db=db_session,
        )

        result = DashboardService().get_latest_month_clients(db=db_session)

        assert result["latest_month"] == "2026-02"
        assert [item["client_name"] for item in result["rows"]] == ["Alpha", "Beta"]
        assert result["rows"][0]["bill_type"] == "预付"
        assert result["rows"][0]["service_type"] == "代投"
        assert result["rows"][0]["consumption"] == 150.0
        assert result["rows"][0]["service_fee_total"] == 10.0
        assert result["rows"][0]["coupon"] == -5.0
        assert result["rows"][0]["month"] == "2026-02"
        assert result["rows"][0]["entity"] == "Entity-A"
        assert result["rows"][0]["owner"] == "Nora"
        assert result["rows"][0]["bill_amount"] == 155.0
        assert result["rows"][0]["note"] is None

    def test_get_latest_month_clients_merges_detail_and_legacy_rows(self, db_session):
        upsert_client_stats_batch(
            "2026-02",
            [
                {"name": "Alpha", "consumption": 120, "fee": 12},
                {"name": "Beta", "consumption": 100, "fee": 10},
            ],
            db=db_session,
        )
        upsert_client_detail_stats_batch(
            "2026-02",
            [
                {
                    "name": "Alpha",
                    "bill_type": "预付",
                    "service_type": "代投",
                    "flow_consumption": 90,
                    "managed_consumption": 30,
                    "net_consumption": 118,
                    "service_fee": 6,
                    "fixed_service_fee": 2,
                    "coupon": 0,
                    "dst": 1,
                    "total": 128,
                }
            ],
            db=db_session,
        )

        result = DashboardService().get_latest_month_clients(db=db_session)

        assert result["latest_month"] == "2026-02"
        assert [item["client_name"] for item in result["rows"]] == ["Alpha", "Beta"]
        alpha = result["rows"][0]
        beta = result["rows"][1]
        assert alpha["bill_type"] == "预付"
        assert beta["bill_type"] == "—"
        assert beta["consumption"] == 100.0
        assert beta["bill_amount"] == 110.0

    def test_update_client_month_note_persists_and_reflects_in_latest_month(self, db_session):
        upsert_client_stats_batch(
            "2026-02",
            [{"name": "Alpha", "consumption": 120, "fee": 12}],
            db=db_session,
        )
        service = DashboardService()
        payload = service.update_client_month_note(
            month="2026-02",
            client_name="Alpha",
            note="需要复核",
            db=db_session,
        )

        assert payload["month"] == "2026-02"
        assert payload["client_name"] == "Alpha"
        assert payload["note"] == "需要复核"

        latest = service.get_latest_month_clients(db=db_session)
        assert latest["rows"][0]["note"] == "需要复核"

    def test_get_client_history_prefers_detail_rows_and_builds_detail_summary(self, db_session):
        db_session.add(
            Client(
                name="Alpha",
                business_type="Agency",
                department="North",
                entity="Entity-A",
                fee_clause="5%",
            )
        )
        db_session.commit()

        upsert_client_detail_stats_batch(
            "2026-02",
            [
                {
                    "name": "Alpha",
                    "bill_type": "预付",
                    "service_type": "代投",
                    "flow_consumption": 80,
                    "managed_consumption": 20,
                    "net_consumption": 96,
                    "service_fee": 5,
                    "fixed_service_fee": 1,
                    "coupon": -2,
                    "dst": 3,
                    "total": 103,
                }
            ],
            db=db_session,
        )
        upsert_client_detail_stats_batch(
            "2026-01",
            [
                {
                    "name": "Alpha",
                    "bill_type": "后付",
                    "service_type": "直客",
                    "flow_consumption": 40,
                    "managed_consumption": 10,
                    "net_consumption": 49,
                    "service_fee": 3,
                    "fixed_service_fee": 2,
                    "coupon": 0,
                    "dst": 1,
                    "total": 55,
                }
            ],
            db=db_session,
        )
        upsert_client_stats_batch(
            "2025-12",
            [{"name": "Alpha", "consumption": 90, "fee": 9}],
            db=db_session,
        )

        result = DashboardService().get_client_history("Alpha", db=db_session)

        assert [item["month"] for item in result["rows"]] == ["2026-02", "2026-01", "2025-12"]
        assert result["rows"][0]["bill_type"] == "预付"
        assert result["rows"][1]["service_type"] == "直客"
        assert result["rows"][2]["consumption"] == 90.0
        assert result["summary"]["total_consumption"] == 240.0
        assert result["summary"]["total_service_fee"] == 20.0
        assert result["summary"]["total_total"] == 257.0

    def test_prepare_result_month_batches_aggregates_multi_bill_type_and_dst_variants(self, db_session):
        service = CalculationService()
        source = pd.DataFrame(
            [
                {
                    "母公司": "Alpha",
                    "预付/后付": "预付",
                    "服务类型": "代投",
                    "流水消耗": 60,
                    "代投消耗": 20,
                    "汇总纯花费": 78,
                    "服务费": 5,
                    "固定服务费": 1,
                    "Coupon": -1,
                    "监管运营费用/数字服务税 (DST)\xa0": 1.5,
                    "汇总": 85.5,
                    "月份归属": "2026-02-01",
                },
                {
                    "母公司": "Alpha",
                    "预付/后付": "后付",
                    "服务类型": "代投",
                    "流水消耗": 40,
                    "代投消耗": 30,
                    "汇总纯花费": 68,
                    "服务费": 4,
                    "固定服务费": 0,
                    "Coupon": 0,
                    "监管运营费用/数字服务税 (DST)\xa0": 1.5,
                    "汇总": 73.5,
                    "月份归属": "2026-02-18",
                },
            ]
        )

        batches = service._prepare_result_month_batches("2026年2月测试_results.xlsx", source)

        assert [month for month, _ in batches] == ["2026-02"]

        month, batch_df = batches[0]
        service._upsert_monthly_stats(month, batch_df, db=db_session)

        result = DashboardService().get_latest_month_clients(db=db_session)
        alpha = next(item for item in result["rows"] if item["client_name"] == "Alpha")

        assert alpha["bill_type"] == "多类型"
        assert alpha["service_type"] == "代投"
        assert alpha["flow_consumption"] == 100.0
        assert alpha["managed_consumption"] == 50.0
        assert alpha["net_consumption"] == 150.0
        assert alpha["dst"] == 3.0
        assert alpha["coupon"] == -1.0
        assert alpha["total"] == 162.0

    def test_prepare_result_month_batches_total_uses_fee_engine_formula(self, db_session):
        service = CalculationService()
        source = pd.DataFrame(
            [
                {
                    "母公司": "Alpha",
                    "预付/后付": "预付",
                    "服务类型": "代投",
                    "流水消耗": 0,
                    "代投消耗": 0,
                    "汇总纯消耗": 100,
                    "换汇汇率": 0.5,
                    "服务费": 1.115,
                    "固定服务费": 0.005,
                    "COUPON": -0.12,
                    "监管运营费用/数字服务税(DST)": 0.3,
                    "月份归属": "2026-02-01",
                }
            ]
        )

        batches = service._prepare_result_month_batches("2026年2月测试_results.xlsx", source)
        month, batch_df = batches[0]
        service._upsert_monthly_stats(month, batch_df, db=db_session)

        result = DashboardService().get_latest_month_clients(db=db_session)
        alpha = next(item for item in result["rows"] if item["client_name"] == "Alpha")

        assert alpha["flow_consumption"] == 0.0
        assert alpha["managed_consumption"] == 0.0
        assert alpha["net_consumption"] == 50.0
        assert alpha["service_fee"] == 1.115
        assert alpha["fixed_service_fee"] == 0.005
        assert alpha["coupon"] == -0.12
        assert alpha["dst"] == 0.3
        assert alpha["total"] == 51.3

    def test_prepare_result_month_batches_total_includes_dst_keyword_variant_header(self, db_session):
        service = CalculationService()
        source = pd.DataFrame(
            [
                {
                    "母公司 ": "Alpha",
                    "预付/后付 ": "预付",
                    "服务类型": "代投",
                    "流水消耗": 80,
                    "代投消耗": 20,
                    "服务费 ": 2,
                    "固定服务费": 1,
                    "coupon": -0.5,
                    "监管费（DST）": 3.2,
                    "月份归属 ": "2026-02-01",
                }
            ]
        )

        batches = service._prepare_result_month_batches("2026年2月测试_results.xlsx", source)
        month, batch_df = batches[0]
        service._upsert_monthly_stats(month, batch_df, db=db_session)

        result = DashboardService().get_latest_month_clients(db=db_session)
        alpha = next(item for item in result["rows"] if item["client_name"] == "Alpha")

        assert alpha["flow_consumption"] == 80.0
        assert alpha["managed_consumption"] == 20.0
        assert alpha["dst"] == 3.2
        assert alpha["coupon"] == -0.5
        assert alpha["total"] == 105.7

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
