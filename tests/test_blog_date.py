"""Tests for blog date parsing and filtering."""

from __future__ import annotations

from builderpulse.sources.blog import _parse_date_utc


def test_parse_naive_date():
    result = _parse_date_utc("2026-06-01")
    assert result is not None
    assert result.tzinfo is None
    assert result.year == 2026
    assert result.month == 6
    assert result.day == 1


def test_parse_aware_date():
    result = _parse_date_utc("2026-06-01T12:00:00+08:00")
    assert result is not None
    assert result.tzinfo is None
    assert result.hour == 4  # 12:00 +08:00 -> 04:00 UTC


def test_parse_invalid():
    assert _parse_date_utc("not a date") is None


def test_parse_empty():
    assert _parse_date_utc("") is None
    assert _parse_date_utc("   ") is None


def test_parse_iso_z():
    result = _parse_date_utc("2026-06-01T12:00:00Z")
    assert result is not None
    assert result.tzinfo is None
    assert result.hour == 12


def test_parse_rfc2822():
    result = _parse_date_utc("Wed, 01 Jun 2026 12:00:00 +0000")
    assert result is not None
    assert result.tzinfo is None
    assert result.year == 2026


def test_parse_negative_offset():
    result = _parse_date_utc("2026-06-01T12:00:00-05:00")
    assert result is not None
    assert result.tzinfo is None
    assert result.hour == 17  # 12:00 -05:00 -> 17:00 UTC
