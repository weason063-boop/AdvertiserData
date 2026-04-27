from __future__ import annotations

from datetime import datetime
from typing import Any

from api.services.daily_fx_snapshot_service import DailyFxSnapshotService
from api.exchange_rate import get_cfets_rates


class ExchangeRateService:
    """
    Read-only FX view service.

    NOTE:
    This service must never trigger live scraping or network fetch.
    It only projects locally persisted daily snapshot data for frontend display.
    """

    def __init__(self, daily_fx_service: DailyFxSnapshotService | None = None):
        self._daily_fx_service = daily_fx_service or DailyFxSnapshotService()

    def _build_hangseng_rows(self, snapshot: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not snapshot:
            return []

        pub_time = str(snapshot.get("pub_time") or snapshot.get("rate_date") or "")
        source = str(snapshot.get("source") or "hangseng_daily_snapshot")

        cny_tt_buy = snapshot.get("cny_tt_buy")
        eur_tt_buy = snapshot.get("eur_tt_buy")
        usd_tt_sell = snapshot.get("usd_tt_sell")
        jpy_tt_sell = snapshot.get("jpy_tt_sell")
        usd_tt_buy = snapshot.get("usd_tt_buy")

        return [
            {
                "currency": "美元 (USD)",
                "code": "USD",
                "tt_buy": str(usd_tt_buy or ""),
                "tt_sell": str(usd_tt_sell or ""),
                "notes_buy": "",
                "notes_sell": "",
                "pub_time": pub_time,
                "source": source,
            },
            {
                "currency": "人民币 (CNY)",
                "code": "CNY",
                "tt_buy": str(cny_tt_buy or ""),
                "tt_sell": "",
                "notes_buy": "",
                "notes_sell": "",
                "pub_time": pub_time,
                "source": source,
            },
            {
                "currency": "欧元 (EUR)",
                "code": "EUR",
                "tt_buy": str(eur_tt_buy or ""),
                "tt_sell": "",
                "notes_buy": "",
                "notes_sell": "",
                "pub_time": pub_time,
                "source": source,
            },
            {
                "currency": "日圆 (JPY)",
                "code": "JPY",
                "tt_buy": "",
                "tt_sell": str(jpy_tt_sell or ""),
                "notes_buy": "",
                "notes_sell": "",
                "pub_time": pub_time,
                "source": source,
            },
        ]

    def _build_cfets_rows(self) -> list[dict[str, Any]]:
        """
        Fetch CFETS rates directly via HTTP request.
        """
        return get_cfets_rates()

    def get_current_rates(self) -> dict[str, list[dict[str, Any]]]:
        payload = self._daily_fx_service.get_today_snapshot_payload()
        snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
        if not isinstance(snapshot, dict):
            snapshot = None

        return {
            "cfets": self._build_cfets_rows(),
            "hangseng": self._build_hangseng_rows(snapshot),
        }
