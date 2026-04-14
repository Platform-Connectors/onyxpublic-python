"""Tests for model validator edge cases and enum parsing."""

from __future__ import annotations

import pytest

from onyxpublic.model import Detection, SystemEvent


def test_detection_parse_severity_rejects_non_string() -> None:
    """Detection severity should reject non-string input values."""

    with pytest.raises(TypeError, match="severity must be an enum name string"):
        Detection.parse_severity(1)


def test_detection_parse_severity_rejects_unknown_name() -> None:
    """Detection severity should reject unknown enum names."""

    with pytest.raises(ValueError, match="Unknown severity name"):
        Detection.parse_severity("NOT_A_VALID_SEVERITY")


def test_system_event_parse_level_accepts_integer_value() -> None:
    """System event level should accept integer enum values."""

    parsed = SystemEvent.parse_level(1)
    assert parsed == 1


def test_system_event_parse_level_rejects_unknown_name() -> None:
    """System event level should reject unknown enum names."""

    with pytest.raises(ValueError, match="Unknown level name"):
        SystemEvent.parse_level("NOT_A_VALID_LEVEL")


def test_system_event_parse_level_rejects_non_string_non_int() -> None:
    """System event level should reject non-string and non-int values."""

    with pytest.raises(TypeError, match="level must be an enum name string or integer"):
        SystemEvent.parse_level(None)


def test_system_event_parse_status_accepts_integer_value() -> None:
    """System event status should accept integer enum values."""

    parsed = SystemEvent.parse_status(1)
    assert parsed == 1


def test_system_event_parse_status_rejects_unknown_name() -> None:
    """System event status should reject unknown enum names."""

    with pytest.raises(ValueError, match="Unknown status name"):
        SystemEvent.parse_status("NOT_A_VALID_STATUS")


def test_system_event_parse_status_rejects_non_string_non_int() -> None:
    """System event status should reject non-string and non-int values."""

    with pytest.raises(
        TypeError,
        match="status must be an enum name string or integer",
    ):
        SystemEvent.parse_status(None)
