from datetime import date, datetime, timedelta

from api.models import FeishuReceivableBill
from api.services.receivable_sync_service import (
    COMPLETED_APPROVAL_STATUS,
    ReceivableSyncService,
    ReceivableTableConfig,
)


_SERVICE = ReceivableSyncService()
BILL_SEND_TABLE_ID = _SERVICE.bill_send_table_id
CLIENT_ADVANCE_TABLE_ID = _SERVICE.client_advance_table_id


def test_receivable_summary_groups_outstanding_and_overdue_by_currency(db_session):
    db_session.add_all(
        [
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="账单发送",
                record_id="rec1",
                flow_type="bill_send",
                client_name="Alpha",
                approval_status="审批中",
                currency="美金USD",
                currency_code="USD",
                amount=100,
                outstanding_amount=100,
                overdue_amount=100,
                overdue_days=3,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
            ),
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="账单发送",
                record_id="rec2",
                flow_type="bill_send",
                client_name="Beta",
                approval_status="已撤回",
                currency="美金USD",
                currency_code="USD",
                amount=200,
                outstanding_amount=0,
                overdue_amount=0,
                overdue_days=0,
                is_active=False,
                is_outstanding=False,
                is_overdue=False,
            ),
            FeishuReceivableBill(
                source_token="app",
                table_id=CLIENT_ADVANCE_TABLE_ID,
                table_name="（客户）垫付申请",
                record_id="rec3",
                flow_type="client_advance",
                client_name="Gamma",
                approval_status="审批中",
                currency="人民币RMB",
                currency_code="RMB",
                amount=50,
                outstanding_amount=50,
                overdue_amount=0,
                overdue_days=0,
                is_active=True,
                is_outstanding=True,
                is_overdue=False,
            ),
        ]
    )
    db_session.commit()

    result = ReceivableSyncService().get_summary(db_session)

    assert result["total_records"] == 3
    assert result["active_records"] == 2
    assert result["outstanding"]["count"] == 2
    assert result["outstanding"]["amount_by_currency"] == [
        {"currency_code": "USD", "currency": "美金USD", "amount": 100.0, "count": 1},
        {"currency_code": "RMB", "currency": "人民币RMB", "amount": 50.0, "count": 1},
    ]
    assert result["overdue"]["count"] == 1
    assert result["overdue"]["max_overdue_days"] == 3
    assert result["overdue"]["aging_buckets"] == [
        {
            "key": "d1_7",
            "label": "1-7天",
            "min_days": 1,
            "max_days": 7,
            "count": 1,
            "amount_by_currency": [
                {"currency_code": "USD", "currency": "美金USD", "amount": 100.0, "count": 1},
            ],
        },
    ]
    assert result["top_overdue"][0]["client_name"] == "Alpha"


def test_receivable_summary_ignores_stale_sources_and_tables(db_session):
    now = datetime.now()
    db_session.add_all(
        [
            FeishuReceivableBill(
                source_token="current_app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="账单发送",
                record_id="current",
                flow_type="bill_send",
                client_name="Current",
                approval_status="审批中",
                currency="USD",
                currency_code="USD",
                amount=100,
                outstanding_amount=100,
                overdue_amount=100,
                overdue_days=2,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
                synced_at=now,
            ),
            FeishuReceivableBill(
                source_token="old_app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="账单发送",
                record_id="old_source",
                flow_type="bill_send",
                client_name="Old Source",
                approval_status="审批中",
                currency="USD",
                currency_code="USD",
                amount=1000,
                outstanding_amount=1000,
                overdue_amount=1000,
                overdue_days=10,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
                synced_at=now - timedelta(days=1),
            ),
            FeishuReceivableBill(
                source_token="current_app",
                table_id="old_table",
                table_name="旧表",
                record_id="old_table",
                flow_type="bill_send",
                client_name="Old Table",
                approval_status="审批中",
                currency="USD",
                currency_code="USD",
                amount=2000,
                outstanding_amount=2000,
                overdue_amount=2000,
                overdue_days=20,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
                synced_at=now + timedelta(seconds=1),
            ),
        ]
    )
    db_session.commit()

    result = ReceivableSyncService().get_summary(db_session)

    assert result["total_records"] == 1
    assert result["outstanding"]["amount_by_currency"] == [
        {"currency_code": "USD", "currency": "USD", "amount": 100.0, "count": 1},
    ]
    assert result["overdue"]["amount_by_currency"] == [
        {"currency_code": "USD", "currency": "USD", "amount": 100.0, "count": 1},
    ]


def test_build_bill_send_row_excludes_rejected_and_completed_records_from_outstanding():
    service = ReceivableSyncService()
    due_date = (date.today() - timedelta(days=5)).isoformat()
    config = ReceivableTableConfig("bill_send", "账单发送", "tbl")

    rejected = service._build_row(
        app_token="app",
        config=config,
        record={
            "record_id": "rejected",
            "fields": {
                "申请状态": "已拒绝",
                "客户简称": "Alpha",
                "币种": "美金USD",
                "账单金额": 100,
                "回款时间": due_date,
            },
        },
        synced_at=datetime.now(),
    )
    completed = service._build_row(
        app_token="app",
        config=config,
        record={
            "record_id": "completed",
            "fields": {
                "申请状态": "已通过",
                "审批节点": "",
                "客户简称": "Alpha",
                "币种": "美金USD",
                "账单金额": 100,
                "回款时间": due_date,
            },
        },
        synced_at=datetime.now(),
    )
    pending = service._build_row(
        app_token="app",
        config=config,
        record={
            "record_id": "pending",
            "fields": {
                "申请状态": "审批中",
                "审批节点": "回款确认",
                "客户简称": "Alpha",
                "币种": "美金USD",
                "账单金额": 100,
                "回款时间": due_date,
            },
        },
        synced_at=datetime.now(),
    )

    assert rejected is not None
    assert rejected.is_active is False
    assert rejected.outstanding_amount == 0
    assert rejected.overdue_amount == 0
    assert completed is not None
    assert completed.outstanding_amount == 0
    assert completed.overdue_amount == 0
    assert pending is not None
    assert pending.outstanding_amount == 100
    assert pending.overdue_amount == 100


def test_client_advance_resource_package_uses_media_quote_amount_when_advance_amount_is_zero():
    service = ReceivableSyncService()
    due_date = (date.today() - timedelta(days=2)).isoformat()
    config = ReceivableTableConfig("client_advance", "（客户）垫付申请", "tbl")

    row = service._build_row(
        app_token="app",
        config=config,
        record={
            "record_id": "resource_package",
            "fields": {
                "申请状态": "审批中",
                "审批节点": "应收账款确认",
                "客户简称": "Alpha",
                "币种": "美金USD",
                "是否为资源包垫付": "全部是",
                "垫付金额(去重)": 0,
                "垫付金额": 0,
                "对客户的媒介报价金额": 1200.5,
                "回款时间1": due_date,
            },
        },
        synced_at=datetime.now(),
    )

    assert row is not None
    assert row.amount == 1200.5
    assert row.outstanding_amount == 1200.5
    assert row.overdue_amount == 1200.5
    assert row.is_outstanding is True
    assert row.is_overdue is True


def test_client_summary_groups_amounts_by_client_and_currency(db_session):
    db_session.add_all(
        [
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="Bill Send",
                record_id="alpha_usd",
                flow_type="bill_send",
                client_name="Alpha",
                owner_name="Ada",
                currency="USD",
                currency_code="USD",
                amount=120,
                outstanding_amount=120,
                overdue_amount=120,
                overdue_days=10,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
            ),
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="Bill Send",
                record_id="alpha_eur",
                flow_type="bill_send",
                client_name="Alpha",
                owner_name="Ada",
                currency="EUR",
                currency_code="EUR",
                amount=80,
                outstanding_amount=80,
                overdue_amount=0,
                overdue_days=0,
                is_active=True,
                is_outstanding=True,
                is_overdue=False,
            ),
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="Bill Send",
                record_id="beta_usd",
                flow_type="bill_send",
                client_name="Beta",
                owner_name="Ben",
                currency="USD",
                currency_code="USD",
                amount=300,
                outstanding_amount=300,
                overdue_amount=0,
                overdue_days=0,
                is_active=True,
                is_outstanding=True,
                is_overdue=False,
            ),
        ]
    )
    db_session.commit()

    result = ReceivableSyncService().get_client_summary(metric="overdue", db=db_session)

    assert result["metric"] == "overdue"
    assert result["rows"][0]["client_name"] == "Alpha"
    assert result["rows"][0]["owner_names"] == ["Ada"]
    assert result["rows"][0]["bill_count"] == 2
    assert result["rows"][0]["outstanding_count"] == 2
    assert result["rows"][0]["overdue_count"] == 1
    assert result["rows"][0]["max_overdue_days"] == 10
    assert result["rows"][0]["outstanding_amount_by_currency"] == [
        {"currency_code": "USD", "currency": "USD", "amount": 120.0, "count": 1},
        {"currency_code": "EUR", "currency": "EUR", "amount": 80.0, "count": 1},
    ]
    assert result["rows"][0]["overdue_amount_by_currency"] == [
        {"currency_code": "USD", "currency": "USD", "amount": 120.0, "count": 1},
    ]


def test_list_bills_filters_by_client_name(db_session):
    db_session.add_all(
        [
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="Bill Send",
                record_id="alpha_1",
                flow_type="bill_send",
                client_name="Alpha",
                application_no="APP-001",
                project_name="Project A",
                currency="USD",
                currency_code="USD",
                amount=100,
                outstanding_amount=100,
                overdue_amount=100,
                overdue_days=5,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
            ),
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="Bill Send",
                record_id="alpha_completed",
                flow_type="bill_send",
                client_name="Alpha",
                application_no="APP-DONE",
                approval_status=COMPLETED_APPROVAL_STATUS,
                project_name="Project Done",
                currency="USD",
                currency_code="USD",
                amount=400,
                outstanding_amount=400,
                overdue_amount=400,
                overdue_days=8,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
            ),
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="Bill Send",
                record_id="beta_1",
                flow_type="bill_send",
                client_name="Beta",
                project_name="Project B",
                currency="USD",
                currency_code="USD",
                amount=200,
                outstanding_amount=200,
                overdue_amount=200,
                overdue_days=6,
                is_active=True,
                is_outstanding=True,
                is_overdue=True,
            ),
            FeishuReceivableBill(
                source_token="app",
                table_id=BILL_SEND_TABLE_ID,
                table_name="Bill Send",
                record_id="alpha_inactive",
                flow_type="bill_send",
                client_name="Alpha",
                project_name="Project C",
                currency="USD",
                currency_code="USD",
                amount=300,
                outstanding_amount=300,
                overdue_amount=300,
                overdue_days=7,
                is_active=False,
                is_outstanding=True,
                is_overdue=True,
            ),
        ]
    )
    db_session.commit()

    rows = ReceivableSyncService().list_bills(
        status="all",
        client_name="Alpha",
        limit=10,
        db=db_session,
    )

    assert len(rows) == 1
    assert rows[0]["client_name"] == "Alpha"
    assert rows[0]["project_name"] == "Project A"
    assert rows[0]["application_no"] == "APP-001"
