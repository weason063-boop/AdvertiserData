import asyncio
import logging
import os
import time
from threading import Lock
from typing import Any, Callable

from api.database import record_operation_audit
from api.services.receivable_sync_service import ReceivableSyncService


logger = logging.getLogger(__name__)
_SYNC_LOCK = Lock()


def receivable_auto_sync_enabled() -> bool:
    """Return whether the backend should run Feishu receivable sync on a timer."""
    if os.getenv("TESTING") == "True":
        return False
    if not _env_bool("FEISHU_RECEIVABLE_AUTO_SYNC_ENABLED", True):
        return False
    if receivable_sync_interval_seconds() <= 0:
        return False
    if not os.getenv("FEISHU_APP_ID") or not os.getenv("FEISHU_APP_SECRET"):
        return False
    return True


def receivable_sync_interval_seconds() -> int:
    return _minutes_env_to_seconds("FEISHU_RECEIVABLE_SYNC_INTERVAL_MINUTES", 30)


def receivable_sync_initial_delay_seconds() -> int:
    return _seconds_env("FEISHU_RECEIVABLE_SYNC_INITIAL_DELAY_SECONDS", 10)


def run_receivable_sync_job(
    *,
    actor: str,
    action: str,
    trigger: str,
    blocking: bool = True,
    metadata: dict[str, Any] | None = None,
    service_factory: Callable[[], ReceivableSyncService] = ReceivableSyncService,
) -> dict[str, Any]:
    """
    Run one Feishu receivable sync behind a process-level lock.

    Manual, event, and scheduled triggers share this lock so they cannot delete
    and rewrite the same snapshot table at the same time.
    """
    audit_metadata = dict(metadata or {})
    audit_metadata["trigger"] = trigger

    acquired = _SYNC_LOCK.acquire(blocking=blocking)
    if not acquired:
        result = {
            "status": "skipped",
            "message": "Feishu receivable sync is already running; this trigger was skipped.",
            "skipped_reason": "sync_already_running",
        }
        record_operation_audit(
            category="feishu",
            action=action,
            actor=actor,
            status="skipped",
            metadata={**audit_metadata, "reason": "sync_already_running"},
        )
        return result

    started_at = time.perf_counter()
    try:
        result = service_factory().sync_all()
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        record_operation_audit(
            category="feishu",
            action=action,
            actor=actor,
            status="success",
            metadata={
                **audit_metadata,
                "duration_ms": duration_ms,
                "synced_records": result.get("synced_records"),
                "table_counts": result.get("table_counts"),
            },
        )
        return result
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        logger.exception("Failed to sync Feishu receivables for trigger=%s", trigger)
        record_operation_audit(
            category="feishu",
            action=action,
            actor=actor,
            status="failed",
            error_message=str(exc),
            metadata={**audit_metadata, "duration_ms": duration_ms},
        )
        raise
    finally:
        _SYNC_LOCK.release()


def start_receivable_sync_scheduler() -> asyncio.Task[None] | None:
    if not receivable_auto_sync_enabled():
        logger.info("Feishu receivable scheduled sync is disabled")
        return None

    interval_seconds = receivable_sync_interval_seconds()
    initial_delay_seconds = receivable_sync_initial_delay_seconds()
    logger.info(
        "Feishu receivable scheduled sync enabled: interval=%ss initial_delay=%ss",
        interval_seconds,
        initial_delay_seconds,
    )
    return asyncio.create_task(_scheduled_sync_loop(), name="feishu-receivable-sync-scheduler")


async def _scheduled_sync_loop() -> None:
    initial_delay = receivable_sync_initial_delay_seconds()
    if initial_delay > 0:
        await asyncio.sleep(initial_delay)

    while True:
        interval_seconds = receivable_sync_interval_seconds()
        if interval_seconds <= 0 or not _env_bool("FEISHU_RECEIVABLE_AUTO_SYNC_ENABLED", True):
            logger.info("Feishu receivable scheduled sync stopped because it was disabled")
            return

        try:
            await asyncio.to_thread(
                run_receivable_sync_job,
                actor="system_scheduler",
                action="scheduled_sync_receivables",
                trigger="scheduled",
                blocking=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled Feishu receivable sync failed")

        await asyncio.sleep(interval_seconds)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _seconds_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return max(0, int(default))
    try:
        return max(0, int(float(raw)))
    except (TypeError, ValueError):
        return max(0, int(default))


def _minutes_env_to_seconds(name: str, default_minutes: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        minutes = float(default_minutes)
    else:
        try:
            minutes = float(raw)
        except (TypeError, ValueError):
            minutes = float(default_minutes)
    if minutes <= 0:
        return 0
    return max(60, int(minutes * 60))
