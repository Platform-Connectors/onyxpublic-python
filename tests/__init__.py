"""Shared test data objects."""

from __future__ import annotations

import datetime

from onyxpublic.api import onyx_pb2
from onyxpublic.common import common_pb2

MOCK_DETECTION = common_pb2.Detection(
    id="det-1",
    latest_position=common_pb2.LatLng(latitude=1.0, longitude=2.0),
    classification="intrusion",
    severity=common_pb2.DETECTION_SEVERITY_LOW,
    latest_od_m=12.3,
    latest_full_position=common_pb2.Position(
        position=common_pb2.LatLng(latitude=1.0, longitude=2.0),
        custom_scale=common_pb2.CustomScale(value=10.0, readable_scale="10m"),
    ),
    node_id="node-1",
    node="segment-a",
    pois=common_pb2.DistanceToZone(
        name="zone-a",
        direction="N",
        separation=12.5,
        notes="ahead",
    ),
)

MOCK_SYSTEM_EVENT = onyx_pb2.SystemEvent(
    event_id="sys-1",
    namespace="system.health",
    title="Test Event",
    level=onyx_pb2.SYSTEM_EVENT_LEVEL_INFO,
    status=onyx_pb2.SYSTEM_EVENT_STATUS_RAISED,
    description="test system event",
)
MOCK_SYSTEM_EVENT.bad_time.FromDatetime(
    datetime.datetime(2026, 1, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
)
MOCK_DETECTION.start_time.FromDatetime(
    datetime.datetime(2025, 1, 1, 0, 0, 0, tzinfo=datetime.timezone.utc)
)
MOCK_DETECTION.last_update_time.FromDatetime(
    datetime.datetime(2025, 1, 1, 0, 0, 10, tzinfo=datetime.timezone.utc)
)
