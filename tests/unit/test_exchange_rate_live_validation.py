# -*- coding: utf-8 -*-
from datetime import datetime

from api import exchange_rate


def _reset_cache():
    exchange_rate._RATE_CACHE = {"hangseng": {"data": [], "timestamp": None}}


def test_has_required_hangseng_fields_complete_payload():
    rows = [
        {"currency": "CNY", "tt_buy": "1.10"},
        {"currency": "USD", "tt_buy": "7.70", "tt_sell": "7.80"},
        {"currency": "JPY", "tt_sell": "0.0502"},
    ]
    assert exchange_rate._has_required_hangseng_fields(rows) is True


def test_has_required_hangseng_fields_missing_jpy():
    rows = [
        {"currency": "CNY", "tt_buy": "1.10"},
        {"currency": "USD", "tt_buy": "7.70", "tt_sell": "7.80"},
    ]
    assert exchange_rate._has_required_hangseng_fields(rows) is False


def test_get_hangseng_rates_fallback_when_live_incomplete(monkeypatch):
    _reset_cache()
    monkeypatch.setattr(
        exchange_rate,
        "get_hangseng_rates_selenium",
        lambda: [{"currency": "USD", "tt_buy": "7.70", "tt_sell": "7.80"}],
    )
    mock_payload = [{"currency": "mock", "source": "hangseng_mock", "pub_time": "2026-03-17 09:30:00 (mock)"}]
    monkeypatch.setattr(exchange_rate, "get_hangseng_rates_mock", lambda: mock_payload)

    result = exchange_rate.get_hangseng_rates()

    assert result == mock_payload
    assert exchange_rate._RATE_CACHE["hangseng"]["data"] == []
    assert exchange_rate._RATE_CACHE["hangseng"]["timestamp"] is None


def test_get_hangseng_rates_cache_only_complete_live(monkeypatch):
    _reset_cache()
    complete_live = [
        {"currency": "CNY", "tt_buy": "1.10", "tt_sell": "1.12", "code": "CNY"},
        {"currency": "USD", "tt_buy": "7.70", "tt_sell": "7.80", "code": "USD"},
        {"currency": "JPY", "tt_buy": "0.0490", "tt_sell": "0.0502", "code": "JPY"},
    ]
    monkeypatch.setattr(exchange_rate, "get_hangseng_rates_selenium", lambda: complete_live)

    first = exchange_rate.get_hangseng_rates()

    assert first
    assert all(item.get("source") == "hangseng_live" for item in first)
    assert exchange_rate._RATE_CACHE["hangseng"]["timestamp"] is not None
    assert isinstance(exchange_rate._RATE_CACHE["hangseng"]["timestamp"], datetime)

    monkeypatch.setattr(
        exchange_rate,
        "get_hangseng_rates_selenium",
        lambda: [{"currency": "USD", "tt_buy": "7.70", "tt_sell": "7.80"}],
    )
    second = exchange_rate.get_hangseng_rates()

    assert second == first


def test_has_required_fields_supports_explicit_code_column():
    rows = [
        {"currency": "ANY_A", "code": "CNY", "tt_buy": "1.10"},
        {"currency": "ANY_B", "code": "USD", "tt_buy": "7.70", "tt_sell": "7.80"},
        {"currency": "ANY_C", "code": "JPY", "tt_sell": "0.0502"},
    ]
    assert exchange_rate._has_required_hangseng_fields(rows) is True
