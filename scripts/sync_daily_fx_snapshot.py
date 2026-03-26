#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Sync today's Hang Seng FX snapshot into local state file.

Usage:
  python scripts/sync_daily_fx_snapshot.py
  python scripts/sync_daily_fx_snapshot.py --force
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.services.daily_fx_snapshot_service import DailyFxSnapshotService  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("sync_daily_fx_snapshot")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync daily FX snapshot")
    parser.add_argument("--force", action="store_true", help="Force overwrite today's snapshot")
    args = parser.parse_args()

    service = DailyFxSnapshotService()
    try:
        snapshot = service.sync_today_snapshot(
            force=args.force,
            actor="scheduler",
            trigger="script",
        )
        payload = service.get_today_snapshot_payload()
        print(
            json.dumps(
                {
                    "status": "ok",
                    "snapshot": snapshot,
                    "sync_state": payload.get("sync_state", {}),
                },
                ensure_ascii=False,
            )
        )
        logger.info("Daily FX snapshot sync succeeded")
        return 0
    except Exception as exc:
        payload = service.get_today_snapshot_payload()
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error": str(exc),
                    "sync_state": payload.get("sync_state", {}),
                },
                ensure_ascii=False,
            )
        )
        logger.exception("Daily FX snapshot sync failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
