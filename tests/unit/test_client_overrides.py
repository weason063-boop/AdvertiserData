# -*- coding: utf-8 -*-

from billing import client_overrides as overrides


def _patch_pre_overrides(monkeypatch, rules):
    monkeypatch.setattr(overrides, "_LOADED", True)
    monkeypatch.setattr(overrides, "_CLIENT_OVERRIDES", rules)
    monkeypatch.setattr(overrides, "_LABEL_ALIASES", {})


def test_media_rate_tt_matches_tiktok_not_ttd(monkeypatch):
    _patch_pre_overrides(
        monkeypatch,
        {
            "云鲸": {
                "action": "media_rate",
                "media": "TT",
                "service_type": "代投",
                "rate": 0.08,
            }
        },
    )

    _, _, tiktok_result = overrides.apply_pre_overrides("任意条款", "TikTok", "代投", "云鲸中东")
    _, _, ttd_result = overrides.apply_pre_overrides("任意条款", "TTD", "代投", "云鲸中东")

    assert tiktok_result == (0.08, 0.0)
    assert ttd_result is None


def test_media_rate_ttd_matches_ttd_not_tiktok(monkeypatch):
    _patch_pre_overrides(
        monkeypatch,
        {
            "云鲸": {
                "action": "media_rate",
                "media": "TTD",
                "service_type": "代投",
                "rate": 0.05,
            }
        },
    )

    _, _, ttd_result = overrides.apply_pre_overrides("任意条款", "TTD", "代投", "云鲸中东")
    _, _, tiktok_result = overrides.apply_pre_overrides("任意条款", "TikTok", "代投", "云鲸中东")

    assert ttd_result == (0.05, 0.0)
    assert tiktok_result is None


def test_exclude_media_tt_excludes_tiktok_not_ttd(monkeypatch):
    _patch_pre_overrides(
        monkeypatch,
        {
            "云鲸": {
                "action": "exclude_media",
                "excluded_media": ["TT"],
            }
        },
    )

    _, _, tiktok_result = overrides.apply_pre_overrides("任意条款", "TikTok", "代投", "云鲸中东")
    _, _, ttd_result = overrides.apply_pre_overrides("任意条款", "TTD", "代投", "云鲸中东")

    assert tiktok_result == (0.0, 0.0)
    assert ttd_result is None
