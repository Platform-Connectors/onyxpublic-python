"""Async Onyx device abstraction with connection and streaming lifecycle."""

from __future__ import annotations

import asyncio
import datetime
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

import grpc
from google.protobuf.json_format import MessageToDict
from pydantic import ValidationError

from .api import onyx_pb2, onyx_pb2_grpc
from .client import create_async_client
from .errors import (
    EventStreamerAlreadyRunningError,
    EventStreamerConnectionError,
    OnyxDeviceNotConnectedError,
    classify_grpc_connection_error,
)
from .model import Detection, OnyxIdentification, SystemEvent

T = TypeVar("T", bound=Detection | Exception)
DetectionCallback = Callable[[Detection], Awaitable[None] | None]
ErrorCallback = Callable[[Exception], Awaitable[None] | None]

_LOGGER = logging.getLogger(__name__)


class AsyncOnyxDevice:
    """Represents one Onyx device and manages connection lifecycle."""

    def __init__(
        self,
        bearer_token: str,
        *,
        host: str,
        port: int | str = 8181,
        using_tls: bool = True,
        server_cert_path: str | None = None,
    ) -> None:
        """Store device connection settings and initialize runtime state."""
        self._address = f"{host}:{port}"
        self._using_tls = using_tls
        self._server_cert_path = server_cert_path
        self._bearer_token = bearer_token

        self._channel: grpc.aio.Channel | None = None
        self._stub: onyx_pb2_grpc.OnyxAsyncStub | None = None

        self._stream_task: asyncio.Task[None] | None = None
        self._stream_call: grpc.aio.UnaryStreamCall | None = None

        self._connected = False
        self._identification: OnyxIdentification | None = None

    @property
    def address(self) -> str:
        """Return host:port for this device."""
        return self._address

    @property
    def connected(self) -> bool:
        """Return True after connect() has completed successfully."""
        return self._connected

    @property
    def identity(self) -> OnyxIdentification | None:
        """Return device identity."""
        return self._identification

    @property
    def is_streaming(self) -> bool:
        """Return True when detection streaming is active."""
        return self._stream_task is not None and not self._stream_task.done()

    async def connect(self) -> None:
        """Connect to the device and cache identification."""
        if self._connected and self._identification is not None:
            return

        await self._disconnect()
        self._channel = create_async_client(
            self._address,
            using_tls=self._using_tls,
            server_cert_path=self._server_cert_path,
            bearer_token=self._bearer_token,
        )
        self._stub = onyx_pb2_grpc.OnyxStub(self._channel)

        try:
            await self.get_identification()
            self._connected = True
        except grpc.aio.AioRpcError as exc:
            await self._disconnect()
            raise classify_grpc_connection_error(
                exc,
                operation="GetIdentification",
            ) from exc

    async def get_identification(self) -> OnyxIdentification:
        """Call GetIdentification once and cache the resulting identity."""
        if self._stub is None:
            raise OnyxDeviceNotConnectedError(
                "Device is not connected; call connect() before get_identification()"
            )

        request = getattr(onyx_pb2, "IdentificationRequest")()
        metadata = self._build_optional_metadata()
        response = await self._stub.GetIdentification(request, metadata=metadata)

        identification = OnyxIdentification(
            manufacturer=response.manufacturer,
            system_type=response.system_type,
            model=response.model,
            serial_number=response.serial_number,
            fiber_number=int(response.fiber_number),
            supported_fibers=response.supported_fibers,
        )

        self._identification = identification
        return identification

    async def get_detections(
        self,
        from_time: datetime.datetime | None = None,
    ) -> list[Detection]:
        """Fetch detections once using the unary GetDetections RPC."""
        if self._stub is None or not self._connected:
            raise OnyxDeviceNotConnectedError(
                "Device is not connected; call connect() before get_detections()"
            )

        request = getattr(onyx_pb2, "DetectionsRequest")()
        if from_time is not None:
            if from_time.tzinfo is None:
                raise ValueError("from_time must be timezone-aware")
            request.since_time.FromDatetime(from_time.astimezone(datetime.timezone.utc))

        response = await self._stub.GetDetections(
            request,
            metadata=self._build_optional_metadata(),
        )

        detections: list[Detection] = []
        for detection in response.detections:
            detection_dict = MessageToDict(
                detection,
                preserving_proto_field_name=True,
            )
            try:
                detections.append(Detection.model_validate(detection_dict))
            except ValidationError as err:
                _LOGGER.error(
                    "Failed to parse detection protobuf into model: %s",
                    err,
                )
                continue
        return detections

    async def get_system_events(self) -> list[SystemEvent]:
        """Fetch current system events once using the unary GetSystemEvents RPC."""
        if self._stub is None or not self._connected:
            raise OnyxDeviceNotConnectedError(
                "Device is not connected; call connect() before get_system_events()"
            )

        request = getattr(onyx_pb2, "SystemEventsRequest")()
        response = await self._stub.GetSystemEvents(
            request,
            metadata=self._build_optional_metadata(),
        )

        events: list[SystemEvent] = []
        for event in response.events:
            event_dict = MessageToDict(
                event,
                preserving_proto_field_name=True,
            )
            try:
                events.append(SystemEvent.model_validate(event_dict))
            except ValidationError as err:
                _LOGGER.error(
                    "Failed to parse system event protobuf into model: %s",
                    err,
                )
                continue
        return events

    async def start_detection_stream(
        self,
        on_detection: DetectionCallback,
        on_error: ErrorCallback | None = None,
        from_seconds_ago: int = 0,
    ) -> None:
        """Start background detection streaming.

        This method does not block the caller after startup and returns once the
        background stream task has been created.
        """
        if self.is_streaming:
            raise EventStreamerAlreadyRunningError(
                "Detection stream is already running"
            )

        self._stream_task = asyncio.create_task(
            self._run_detection_stream(on_detection, from_seconds_ago, on_error),
            name="onyx-device-detection-stream",
        )

    async def stop_detection_stream(self) -> None:
        """Stop active detection streaming if running."""
        if self._stream_call is not None:
            self._stream_call.cancel()

        task = self._stream_task
        if task is not None:
            task.cancel()
            try:
                await task
            except grpc.aio.AioRpcError:
                pass
            except asyncio.CancelledError:
                pass

    async def close(self) -> None:
        """Stop background work and mark the device disconnected."""
        await self.stop_detection_stream()
        await self._disconnect()

    def _build_optional_metadata(self) -> tuple[tuple[str, str], ...] | None:
        """Build per-call auth metadata for insecure token-based connections."""
        if self._using_tls or not self._bearer_token:
            return None
        return (("authorization", f"Bearer {self._bearer_token}"),)

    def _build_stream_request(
        self, from_seconds_ago: int
    ) -> onyx_pb2.StreamDetectionsRequest:
        """Create a StreamDetectionsRequest with optional historical start time."""
        request = getattr(onyx_pb2, "StreamDetectionsRequest")()
        if from_seconds_ago > 0:
            from_time = datetime.datetime.now(
                datetime.timezone.utc
            ) - datetime.timedelta(seconds=from_seconds_ago)
            request.from_time.FromDatetime(from_time)
        return request

    async def _disconnect(self) -> None:
        """Reset connection state and close the active channel if present."""
        self._connected = False
        self._stub = None

        if self._channel is not None:
            await self._channel.close()
            self._channel = None

    async def _run_detection_stream(
        self,
        on_detection: DetectionCallback,
        from_seconds_ago: int,
        on_error: ErrorCallback | None,
    ) -> None:
        """Consume stream responses and dispatch detection/error callbacks."""
        try:
            if self._stub is None or not self._connected:
                exc = EventStreamerConnectionError(
                    "Detection stream requires an active device connection"
                )
                if on_error is not None:
                    await self._call_callback(on_error, exc)
                return

            request = self._build_stream_request(from_seconds_ago)
            self._stream_call = self._stub.StreamDetections(
                request,
                metadata=self._build_optional_metadata(),
            )

            async for response in self._stream_call:
                for detection in response.detections:
                    detection_dict = MessageToDict(
                        detection, preserving_proto_field_name=True
                    )
                    try:
                        print(detection_dict)
                        detection_model = Detection.model_validate(detection_dict)
                    except ValidationError as err:
                        _LOGGER.error(
                            "Failed to parse detection protobuf into model: %s",
                            err,
                        )
                        continue
                    await self._call_callback(on_detection, detection_model)

        except grpc.aio.AioRpcError as exc:
            if exc.code() is not grpc.StatusCode.CANCELLED and on_error is not None:
                await self._call_callback(on_error, exc)

        finally:
            if self._stream_call is not None:
                self._stream_call.cancel()
            self._stream_call = None

    async def _call_callback(
        self, callback: Callable[[T], Awaitable[None] | None], arg: T
    ) -> None:
        """Invoke a callback and await it when it returns a coroutine."""
        result = callback(arg)
        if asyncio.iscoroutine(result):
            await result
