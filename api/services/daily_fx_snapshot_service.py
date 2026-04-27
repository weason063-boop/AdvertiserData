from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from api.database import record_operation_audit

logger = logging.getLogger(__name__)


class DailyFxSnapshotService:
    TIMEZONE = ZoneInfo("Asia/Shanghai")

    def __init__(self, state_path: Path | None = None):
        self._state_path_override = state_path
        self._lock = threading.Lock()

    def _audit(
        self,
        *,
        action: str,
        actor: str,
        status: str,
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
        rate_date: str | None = None,
    ) -> None:
        record_operation_audit(
            category="fx_snapshot",
            action=action,
            actor=actor,
            status=status,
            result_ref=rate_date,
            error_message=error_message,
            metadata=metadata,
        )

    def _get_upload_dir(self) -> Path:
        upload_dir = Path(__file__).parent.parent.parent / "uploads"
        upload_dir.mkdir(exist_ok=True)
        return upload_dir

    def _get_state_path(self) -> Path:
        if self._state_path_override is not None:
            self._state_path_override.parent.mkdir(parents=True, exist_ok=True)
            return self._state_path_override
        return self._get_upload_dir() / "hangseng_daily_fx_state.json"

    def _now(self) -> datetime:
        return datetime.now(self.TIMEZONE)

    def _today_key(self) -> str:
        return self._now().strftime("%Y-%m-%d")

    def _default_state(self) -> dict[str, Any]:
        return {
            "snapshots": {},
        }

    def _load_state_unlocked(self) -> dict[str, Any]:
        path = self._get_state_path()
        if not path.exists():
            return self._default_state()
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to parse FX snapshot state file, fallback to default", exc_info=True)
            return self._default_state()

        if not isinstance(payload, dict):
            return self._default_state()

        state = self._default_state()
        snapshots = payload.get("snapshots")
        if isinstance(snapshots, dict):
            normalized = {}
            for key, value in snapshots.items():
                if not isinstance(key, str) or not isinstance(value, dict):
                    continue
                normalized[key] = value
            state["snapshots"] = normalized

        return state

    def _save_state_unlocked(self, state: dict[str, Any]) -> None:
        path = self._get_state_path()
        tmp_path = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
        serialized = json.dumps(state, ensure_ascii=False, indent=2)
        tmp_path.write_text(serialized, encoding="utf-8")
        last_exc: Exception | None = None
        for attempt in range(1, 6):
            try:
                tmp_path.replace(path)
                return
            except PermissionError as exc:
                last_exc = exc
                if attempt >= 5:
                    break
                time.sleep(0.1 * attempt)
        # Fallback to direct write when atomic replace is blocked by file locks.
        if last_exc is not None:
            try:
                path.write_text(serialized, encoding="utf-8")
                return
            except Exception:
                logger.warning("Direct state write fallback failed for %s", path, exc_info=True)

        if tmp_path.exists():
            try:
                tmp_path.unlink(missing_ok=True)
            except PermissionError:
                logger.warning("Failed to clean temporary FX state file: %s", tmp_path, exc_info=True)
        if last_exc is not None:
            raise last_exc

    def get_today_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            state = self._load_state_unlocked()
            snapshot = state["snapshots"].get(self._today_key())
            return snapshot if isinstance(snapshot, dict) else None

    def get_today_snapshot_payload(self) -> dict[str, Any]:
        with self._lock:
            state = self._load_state_unlocked()
            today = self._today_key()
            snapshot = state["snapshots"].get(today)
            has_snapshot = isinstance(snapshot, dict)
            return {
                "date": today,
                "has_snapshot": has_snapshot,
                "snapshot": snapshot if has_snapshot else None,
            }

    def list_snapshots(self, limit: int = 14) -> list[dict[str, Any]]:
        safe_limit = max(1, min(90, int(limit or 14)))
        with self._lock:
            state = self._load_state_unlocked()
            items = []
            for date_key, snapshot in state["snapshots"].items():
                if not isinstance(snapshot, dict):
                    continue
                row = {"date": str(date_key)}
                row.update(snapshot)
                items.append(row)

        items.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
        return items[:safe_limit]

    def upsert_snapshot(
        self,
        rate_date: str,
        cny_tt_buy: float,
        eur_tt_buy: float,
        usd_tt_sell: float,
        jpy_tt_sell: float,
        usd_tt_buy: float,
        *,
        actor: str = "system",
    ) -> dict[str, Any]:
        try:
            date_obj = datetime.strptime(rate_date, "%Y-%m-%d")
            normalized_date = date_obj.strftime("%Y-%m-%d")
        except Exception as exc:
            self._audit(
                action="upsert_daily_snapshot",
                actor=actor,
                status="failed",
                rate_date=rate_date,
                error_message=f"Invalid rate_date: {rate_date}",
            )
            raise ValueError(f"Invalid rate_date: {rate_date}") from exc

        values = {
            "cny_tt_buy": float(cny_tt_buy),
            "eur_tt_buy": float(eur_tt_buy),
            "usd_tt_sell": float(usd_tt_sell),
            "jpy_tt_sell": float(jpy_tt_sell),
            "usd_tt_buy": float(usd_tt_buy),
        }
        for key, value in values.items():
            if value <= 0:
                self._audit(
                    action="upsert_daily_snapshot",
                    actor=actor,
                    status="failed",
                    rate_date=normalized_date,
                    error_message=f"{key} must be positive",
                )
                raise ValueError(f"{key} must be positive")

        now = self._now()
        snapshot = {
            "rate_date": normalized_date,
            "cny_tt_buy": values["cny_tt_buy"],
            "eur_tt_buy": values["eur_tt_buy"],
            "usd_tt_sell": values["usd_tt_sell"],
            "jpy_tt_sell": values["jpy_tt_sell"],
            "usd_tt_buy": values["usd_tt_buy"],
            "source": "manual",
            "pub_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with self._lock:
            state = self._load_state_unlocked()
            state["snapshots"][normalized_date] = snapshot
            self._save_state_unlocked(state)

        self._audit(
            action="upsert_daily_snapshot",
            actor=actor,
            status="success",
            rate_date=normalized_date,
            metadata={
                "source": "manual",
                "cny_tt_buy": values["cny_tt_buy"],
                "eur_tt_buy": values["eur_tt_buy"],
                "usd_tt_sell": values["usd_tt_sell"],
                "jpy_tt_sell": values["jpy_tt_sell"],
                "usd_tt_buy": values["usd_tt_buy"],
            },
        )

        return snapshot
