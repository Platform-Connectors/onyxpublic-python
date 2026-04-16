"""Detection model definition."""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum

from pydantic import BaseModel, field_validator


class OnyxIdentification(BaseModel):
    """Identification values returned by GetIdentification."""

    manufacturer: str
    system_type: str
    model: str
    serial_number: str
    fiber_number: int
    supported_fibers: int


class DetectionSeverity(IntEnum):
    """Detection severity levels mirrored from the protobuf enum values."""

    DETECTION_SEVERITY_UNSPECIFIED = 0
    DETECTION_SEVERITY_LOW = 1
    DETECTION_SEVERITY_MEDIUM = 2
    DETECTION_SEVERITY_HIGH = 3


class LatLng(BaseModel):
    """Latitude/longitude coordinates."""

    latitude: float
    longitude: float


class CustomScale(BaseModel):
    """Custom distance scale representation for a detection position."""

    value: float
    readable_scale: str


class Position(BaseModel):
    """Full position including geographic coordinates and custom scale metadata."""

    position: LatLng
    custom_scale: CustomScale


class CardinalDirection(StrEnum):
    """Cardinal direction names with short-code API values."""

    North = "N"
    South = "S"
    East = "E"
    West = "W"


class DistanceToZone(BaseModel):
    """Distance details between a detection and a named zone."""

    name: str | None = None
    direction: CardinalDirection | None = None
    separation: float | None = None
    notes: str | None = None


class Detection(BaseModel):
    """Normalized detection payload parsed from protobuf-derived dictionaries."""

    id: str
    start_time: datetime
    last_update_time: datetime
    latest_position: LatLng
    classification: str
    severity: DetectionSeverity
    latest_od_m: float
    latest_full_position: Position
    node_id: str
    node: str | None = None
    pois: DistanceToZone | None = None

    @field_validator("severity", mode="before")
    @classmethod
    def parse_severity(cls, value: object) -> DetectionSeverity:
        """Parse severity from enum name string to DetectionSeverity enum value."""
        if not isinstance(value, str):
            raise TypeError("severity must be an enum name string")

        text = value.strip()

        try:
            return DetectionSeverity[text]
        except KeyError as exc:
            allowed = ", ".join(member.name for member in DetectionSeverity)
            raise ValueError(
                f"Unknown severity name '{text}'. Expected one of: {allowed}"
            ) from exc


class SystemEventStatus(IntEnum):
    """System event lifecycle states mirrored from protobuf enum values."""

    SYSTEM_EVENT_STATUS_UNSPECIFIED = 0
    SYSTEM_EVENT_STATUS_RAISED = 1
    SYSTEM_EVENT_STATUS_RAISED_ACKED = 2
    SYSTEM_EVENT_STATUS_RESOLVED = 3
    SYSTEM_EVENT_STATUS_RESOLVED_ACKED = 4


class SystemEventLevel(IntEnum):
    """System event severity levels mirrored from protobuf enum values."""

    SYSTEM_EVENT_LEVEL_UNSPECIFIED = 0
    SYSTEM_EVENT_LEVEL_HIGH = 1
    SYSTEM_EVENT_LEVEL_LOW = 2
    SYSTEM_EVENT_LEVEL_INFO = 3
    SYSTEM_EVENT_LEVEL_CRITICAL = 4


class SystemEvent(BaseModel):
    """Normalized system event payload parsed from protobuf-derived dictionaries."""

    event_id: str
    namespace: str
    title: str
    level: SystemEventLevel
    description: str
    consequence: str | None = None
    how_to_resolve: str | None = None
    who_can_resolve: str | None = None
    url: str | None = None
    status: SystemEventStatus
    bad_time: datetime | None = None
    bad_acked_time: datetime | None = None
    resolved_time: datetime | None = None
    resolved_acked_time: datetime | None = None
    additional_msg: str | None = None
    reportable: bool = False
    reportable_after: str | None = None

    @field_validator("level", mode="before")
    @classmethod
    def parse_level(cls, value: object) -> SystemEventLevel:
        """Parse level from enum name or integer into SystemEventLevel."""
        if isinstance(value, str):
            try:
                return SystemEventLevel[value.strip()]
            except KeyError as exc:
                allowed = ", ".join(member.name for member in SystemEventLevel)
                raise ValueError(
                    f"Unknown level name '{value}'. Expected one of: {allowed}"
                ) from exc
        if isinstance(value, int):
            return SystemEventLevel(value)
        raise TypeError("level must be an enum name string or integer")

    @field_validator("status", mode="before")
    @classmethod
    def parse_status(cls, value: object) -> SystemEventStatus:
        """Parse status from enum name or integer into SystemEventStatus."""
        if isinstance(value, str):
            try:
                return SystemEventStatus[value.strip()]
            except KeyError as exc:
                allowed = ", ".join(member.name for member in SystemEventStatus)
                raise ValueError(
                    f"Unknown status name '{value}'. Expected one of: {allowed}"
                ) from exc
        if isinstance(value, int):
            return SystemEventStatus(value)
        raise TypeError("status must be an enum name string or integer")
