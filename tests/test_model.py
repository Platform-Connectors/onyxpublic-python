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


@pytest.mark.parametrize(
    ("parser", "value"),
    [
        (SystemEvent.parse_level, 1),
        (SystemEvent.parse_status, 1),
    ],
)
def test_system_event_parsers_accept_integer_value(parser, value: int) -> None:
    """System event parser helpers should accept integer enum values."""

    parsed = parser(value)
    assert parsed == value


@pytest.mark.parametrize(
    ("parser", "value", "error_type", "error_message"),
    [
        (
            SystemEvent.parse_level,
            "NOT_A_VALID_LEVEL",
            ValueError,
            "Unknown level name",
        ),
        (
            SystemEvent.parse_status,
            "NOT_A_VALID_STATUS",
            ValueError,
            "Unknown status name",
        ),
        (
            SystemEvent.parse_level,
            None,
            TypeError,
            "level must be an enum name string or integer",
        ),
        (
            SystemEvent.parse_status,
            None,
            TypeError,
            "status must be an enum name string or integer",
        ),
    ],
)
def test_system_event_parsers_reject_invalid_values(
    parser,
    value: object,
    error_type: type[Exception],
    error_message: str,
) -> None:
    """System event parser helpers should reject invalid names and unsupported types."""

    with pytest.raises(error_type, match=error_message):
        parser(value)
