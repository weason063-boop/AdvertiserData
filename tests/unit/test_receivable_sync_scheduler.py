from api.services import receivable_sync_scheduler as scheduler


def test_receivable_auto_sync_disabled_in_testing(monkeypatch):
    monkeypatch.setenv("TESTING", "True")
    monkeypatch.setenv("FEISHU_APP_ID", "app_id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app_secret")
    monkeypatch.delenv("FEISHU_RECEIVABLE_AUTO_SYNC_ENABLED", raising=False)

    assert scheduler.receivable_auto_sync_enabled() is False


def test_receivable_auto_sync_enabled_when_credentials_exist(monkeypatch):
    monkeypatch.setenv("TESTING", "False")
    monkeypatch.setenv("FEISHU_APP_ID", "app_id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app_secret")
    monkeypatch.delenv("FEISHU_RECEIVABLE_AUTO_SYNC_ENABLED", raising=False)
    monkeypatch.delenv("FEISHU_RECEIVABLE_SYNC_INTERVAL_MINUTES", raising=False)

    assert scheduler.receivable_auto_sync_enabled() is True
    assert scheduler.receivable_sync_interval_seconds() == 30 * 60


def test_receivable_auto_sync_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("TESTING", "False")
    monkeypatch.setenv("FEISHU_APP_ID", "app_id")
    monkeypatch.setenv("FEISHU_APP_SECRET", "app_secret")
    monkeypatch.setenv("FEISHU_RECEIVABLE_AUTO_SYNC_ENABLED", "false")

    assert scheduler.receivable_auto_sync_enabled() is False


def test_run_receivable_sync_job_records_success(monkeypatch):
    audits = []
    monkeypatch.setattr(scheduler, "record_operation_audit", lambda **kwargs: audits.append(kwargs))

    class FakeService:
        def sync_all(self):
            return {
                "status": "ok",
                "synced_records": 3,
                "table_counts": {"bill_send": 2, "client_advance": 1},
            }

    result = scheduler.run_receivable_sync_job(
        actor="tester",
        action="scheduled_sync_receivables",
        trigger="scheduled",
        service_factory=FakeService,
    )

    assert result["status"] == "ok"
    assert audits[0]["status"] == "success"
    assert audits[0]["metadata"]["trigger"] == "scheduled"
    assert audits[0]["metadata"]["synced_records"] == 3


def test_run_receivable_sync_job_skips_when_another_sync_is_running(monkeypatch):
    audits = []
    monkeypatch.setattr(scheduler, "record_operation_audit", lambda **kwargs: audits.append(kwargs))
    scheduler._SYNC_LOCK.acquire()
    try:
        result = scheduler.run_receivable_sync_job(
            actor="tester",
            action="event_sync_receivables",
            trigger="event",
            blocking=False,
        )
    finally:
        scheduler._SYNC_LOCK.release()

    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "sync_already_running"
    assert audits[0]["status"] == "skipped"
    assert audits[0]["metadata"]["reason"] == "sync_already_running"
