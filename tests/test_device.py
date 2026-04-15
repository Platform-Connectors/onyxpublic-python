"""Pytest coverage for AsyncOnyxDevice connection and unary RPC behavior."""

from __future__ import annotations

import asyncio
import datetime
from collections.abc import Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import grpc
import pytest

from onyxpublic.api import onyx_pb2
from onyxpublic.device import AsyncOnyxDevice
from onyxpublic.errors import (
    AuthError,
    ConnectError,
    DeviceNotConnectedError,
    EventStreamerAlreadyRunningError,
    EventStreamerConnectionError,
    OnyxPublicError,
)
from onyxpublic.model import OnyxIdentification, SystemEvent

from .conftest import FakeChannel, MockOnyxStub, RpcErrorFactory


class _AsyncStreamCall:
    """Simple async-iterable stream call test double."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        """Store stream responses to yield during async iteration."""
        self._responses = responses
        self._index = 0

    def __aiter__(self) -> _AsyncStreamCall:
        """Return self as an async iterator."""
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Yield next response or stop iteration when exhausted."""
        if self._index >= len(self._responses):
            raise StopAsyncIteration
        item = self._responses[self._index]
        self._index += 1
        return item

    def cancel(self) -> None:
        """Cancel the stream call (no-op for test double)."""
        pass


class _RaisingAsyncStreamCall:
    """Async-iterable stream call that raises a gRPC error while iterating."""

    def __init__(self, error: grpc.aio.AioRpcError) -> None:
        """Store the error to raise from the async iterator."""
        self._error = error

    def __aiter__(self) -> _RaisingAsyncStreamCall:
        """Return self as an async iterator."""
        return self

    async def __anext__(self) -> SimpleNamespace:
        """Raise the configured stream error on first iteration."""
        raise self._error

    def cancel(self) -> None:
        """Cancel the stream call (no-op for test double)."""
        pass


def _valid_detection_payload() -> dict[str, object]:
    """Return a minimal payload that satisfies the Detection model."""

    return {
        "id": "det-1",
        "start_time": "2025-01-01T00:00:00Z",
        "last_update_time": "2025-01-01T00:00:10Z",
        "latest_position": {"latitude": 1.0, "longitude": 2.0},
        "classification": "intrusion",
        "severity": "DETECTION_SEVERITY_LOW",
        "latest_od_m": 12.3,
        "latest_full_position": {
            "position": {"latitude": 1.0, "longitude": 2.0},
            "custom_scale": {"value": 10.0, "readable_scale": "10m"},
        },
        "node_id": "node-1",
        "node": "segment-a",
    }


async def test_device_properties_expose_address_and_identity(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """address and identity properties should reflect internal state."""

    device = device_factory(port=9191)

    assert device.address == "127.0.0.1:9191"
    assert device.identity is None


@pytest.mark.parametrize(
    ("code", "details", "expected_type", "expected_reason"),
    [
        (
            grpc.StatusCode.UNAUTHENTICATED,
            "token signature is invalid",
            AuthError,
            "authentication",
        ),
        (
            grpc.StatusCode.UNAVAILABLE,
            "connection refused",
            ConnectError,
            "connection_refused",
        ),
        (
            grpc.StatusCode.DEADLINE_EXCEEDED,
            "request timed out",
            ConnectError,
            "timeout",
        ),
        (
            grpc.StatusCode.UNAVAILABLE,
            "upstream service unavailable",
            ConnectError,
            "transport_unavailable",
        ),
        (
            grpc.StatusCode.INTERNAL,
            "internal server error",
            EventStreamerConnectionError,
            "grpc_error",
        ),
    ],
)
async def test_connect_maps_grpc_errors(
    device_factory: Callable[..., AsyncOnyxDevice],
    patched_onyx_stub: MockOnyxStub,
    fake_channel: FakeChannel,
    make_rpc_error: RpcErrorFactory,
    code: grpc.StatusCode,
    details: str,
    expected_type: type[OnyxPublicError],
    expected_reason: str,
) -> None:
    """connect() should map gRPC failures to stable library exceptions."""

    patched_onyx_stub.GetIdentification = AsyncMock(
        side_effect=make_rpc_error(code, details)
    )

    device = device_factory(using_tls=False)

    with pytest.raises(expected_type) as exc_info:
        await device.connect()

    assert exc_info.value.code == code.name
    assert exc_info.value.reason == expected_reason
    fake_channel.close.assert_awaited_once()


async def test_optional_metadata_is_set_only_for_insecure_token(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """Authorization metadata should be attached only for insecure token calls."""

    insecure_with_token = device_factory(using_tls=False)
    tls_with_token = device_factory(using_tls=True)

    assert insecure_with_token._build_optional_metadata() == (
        ("authorization", "Bearer token"),
    )
    assert tls_with_token._build_optional_metadata() is None


async def test_build_stream_request_sets_from_time_only_when_positive(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """_build_stream_request() should populate from_time only for positive values."""

    device = device_factory()

    no_history = device._build_stream_request(0)
    with_history = device._build_stream_request(15)

    assert no_history.HasField("from_time") is False
    assert with_history.HasField("from_time") is True


async def test_connect_returns_early_when_already_connected(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """connect() should return immediately when state is already initialized."""

    device = device_factory()
    device._connected = True
    device._identification = OnyxIdentification(
        manufacturer="Sintela",
        system_type="Onyx",
        model="95-2",
        serial_number="ABC123",
        fiber_number=1,
        supported_fibers=2,
    )

    await device.connect()
    assert device.connected is True


async def test_connect_populates_identity(
    device_factory: Callable[..., AsyncOnyxDevice],
    patched_onyx_stub: MockOnyxStub,
) -> None:
    """connect() should set connected state and cache parsed identification."""

    patched_onyx_stub.GetIdentification = AsyncMock(
        return_value=onyx_pb2.IdentificationResponse(
            manufacturer="Sintela",
            system_type="Onyx",
            model="95-2",
            serial_number="ABC123",
            fiber_number=onyx_pb2.FIBER_NUMBER_1,
            supported_fibers=2,
        )
    )

    device = device_factory(using_tls=False)
    await device.connect()

    assert device.connected is True
    assert device.identity is not None
    assert device.identity.serial_number == "ABC123"


@pytest.mark.parametrize(
    "method_name",
    ["get_identification", "get_detections", "get_system_events"],
)
async def test_methods_require_connected_device(
    device_factory: Callable[..., AsyncOnyxDevice],
    method_name: str,
) -> None:
    """Public RPC helpers should fail fast when the device is not connected."""

    device = device_factory()
    method = getattr(device, method_name)

    with pytest.raises(DeviceNotConnectedError):
        await method()


async def test_get_detections_rejects_naive_from_time(
    mock_device: AsyncOnyxDevice,
) -> None:
    """get_detections() should require timezone-aware from_time values."""

    with pytest.raises(ValueError, match="timezone-aware"):
        await mock_device.get_detections(from_time=datetime.datetime.now())


async def test_get_detections_skips_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
) -> None:
    """Invalid detection payloads should be logged and skipped, not raised."""

    stub = fake_onyx_stub
    stub.GetDetections = AsyncMock(return_value=SimpleNamespace(detections=[object()]))
    monkeypatch.setattr(
        "onyxpublic.device.MessageToDict",
        lambda *args, **kwargs: {"id": "missing-required-fields"},
    )

    detections = await mock_device.get_detections()
    assert detections == []


async def test_get_detections_parses_valid_payloads_and_since_time(
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
    mock_detection,
) -> None:
    """get_detections() should parse valid payloads and support aware since time."""

    fake_onyx_stub.GetDetections = AsyncMock(
        return_value=onyx_pb2.DetectionsResponse(detections=[mock_detection])
    )

    from_time = datetime.datetime.now(datetime.timezone.utc)
    detections = await mock_device.get_detections(from_time=from_time)

    assert len(detections) == 1
    assert detections[0].id == "det-1"


async def test_get_detections_resets_connection_on_rpc_error(
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
    make_rpc_error: RpcErrorFactory,
) -> None:
    """get_detections() should close the device when the RPC failure requires reset."""

    fake_onyx_stub.GetDetections = AsyncMock(
        side_effect=make_rpc_error(
            grpc.StatusCode.UNAVAILABLE,
            "stream unavailable",
        )
    )
    mock_device.close = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(ConnectError) as exc_info:
        await mock_device.get_detections()

    assert exc_info.value.reason == "transport_unavailable"
    mock_device.close.assert_awaited_once()


async def test_get_system_events_skips_invalid_payloads(
    monkeypatch: pytest.MonkeyPatch,
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
) -> None:
    """Invalid system event payloads should be logged and skipped."""

    fake_onyx_stub.GetSystemEvents = AsyncMock(
        return_value=SimpleNamespace(events=[object()])
    )
    monkeypatch.setattr(
        "onyxpublic.device.MessageToDict",
        lambda *args, **kwargs: {"event_id": "missing-required-fields"},
    )

    events = await mock_device.get_system_events()
    assert events == []


async def test_get_system_events_returns_models(
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
    mock_system_event,
) -> None:
    """get_system_events() should parse unary RPC payloads into SystemEvent models."""

    stub = fake_onyx_stub
    stub.GetSystemEvents = AsyncMock(
        return_value=onyx_pb2.SystemEventsResponse(events=[mock_system_event])
    )

    events = await mock_device.get_system_events()

    assert len(events) == 1
    assert isinstance(events[0], SystemEvent)
    assert events[0].event_id == "sys-1"


async def test_get_system_events_resets_connection_on_rpc_error(
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
    make_rpc_error: RpcErrorFactory,
) -> None:
    """get_system_events() should close the device on resettable RPC failures."""

    fake_onyx_stub.GetSystemEvents = AsyncMock(
        side_effect=make_rpc_error(
            grpc.StatusCode.INTERNAL,
            "internal server error",
        )
    )
    mock_device.close = AsyncMock()  # type: ignore[method-assign]

    with pytest.raises(EventStreamerConnectionError) as exc_info:
        await mock_device.get_system_events()

    assert exc_info.value.reason == "grpc_error"
    mock_device.close.assert_awaited_once()


async def test_start_detection_stream_raises_when_already_running(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """start_detection_stream() should guard against duplicate stream startup."""

    device = device_factory()
    device._stream_task = asyncio.create_task(asyncio.sleep(3600))

    with pytest.raises(EventStreamerAlreadyRunningError):
        device.start_detection_stream(lambda _d: None)

    device._stream_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await device._stream_task


async def test_start_detection_stream_creates_background_task(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """start_detection_stream() should create a background stream task."""

    device = device_factory()
    device._connected = True
    device._stub = MockOnyxStub()  # type: ignore[assignment]

    device.start_detection_stream(lambda _d: None)

    assert device.is_streaming is True
    await device.stop_detection_stream()


async def test_stop_detection_stream_cancels_call_and_task(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """stop_detection_stream() should cancel both active RPC call and stream task."""

    device = device_factory()

    stream_call = SimpleNamespace(cancel=Mock())
    stream_task = asyncio.create_task(asyncio.sleep(3600))

    device._stream_call = stream_call  # type: ignore[assignment]
    device._stream_task = stream_task

    await device.stop_detection_stream()

    stream_call.cancel.assert_called_once()
    assert stream_task.cancelled()


async def test_stop_detection_stream_swallows_grpc_task_errors(
    device_factory: Callable[..., AsyncOnyxDevice],
    make_rpc_error: RpcErrorFactory,
) -> None:
    """stop_detection_stream() should ignore stream task gRPC failures."""

    device = device_factory()

    async def _raise_rpc_error() -> None:
        raise make_rpc_error(grpc.StatusCode.UNAVAILABLE, "stream broken")

    device._stream_task = asyncio.create_task(_raise_rpc_error())
    await asyncio.sleep(0)

    await device.stop_detection_stream()


async def test_run_detection_stream_reports_missing_connection(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """Internal stream loop should surface disconnected state through on_error."""

    device = device_factory()
    on_error = AsyncMock()

    await device._run_detection_stream(
        on_detection=lambda _d: None,
        from_seconds_ago=0,
        on_error=on_error,
    )

    on_error.assert_awaited_once()
    await_args = on_error.await_args
    assert await_args is not None
    received_exc = await_args.args[0]
    assert isinstance(received_exc, EventStreamerConnectionError)


async def test_run_detection_stream_dispatches_valid_detections(
    monkeypatch: pytest.MonkeyPatch,
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
) -> None:
    """Stream loop should validate payloads and dispatch detection callbacks."""

    fake_onyx_stub.StreamDetections = Mock(
        return_value=_AsyncStreamCall([SimpleNamespace(detections=[object()])])
    )
    monkeypatch.setattr(
        "onyxpublic.device.MessageToDict",
        lambda *args, **kwargs: _valid_detection_payload(),
    )
    on_detection = AsyncMock()

    await mock_device._run_detection_stream(
        on_detection=on_detection,
        from_seconds_ago=5,
        on_error=None,
    )

    on_detection.assert_awaited_once()


async def test_run_detection_stream_skips_invalid_detection_payloads(
    monkeypatch: pytest.MonkeyPatch,
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
) -> None:
    """Invalid stream payloads should be skipped without callback invocation."""

    fake_onyx_stub.StreamDetections = Mock(
        return_value=_AsyncStreamCall([SimpleNamespace(detections=[object()])])
    )
    monkeypatch.setattr(
        "onyxpublic.device.MessageToDict",
        lambda *args, **kwargs: {"id": "invalid"},
    )
    on_detection = AsyncMock()

    await mock_device._run_detection_stream(
        on_detection=on_detection,
        from_seconds_ago=0,
        on_error=None,
    )

    on_detection.assert_not_awaited()


@pytest.mark.parametrize(
    ("code", "details", "expects_error_callback", "expects_close", "expected_reason"),
    [
        (
            grpc.StatusCode.CANCELLED,
            "client cancelled",
            False,
            False,
            None,
        ),
        (
            grpc.StatusCode.UNAVAILABLE,
            "stream unavailable",
            True,
            True,
            "transport_unavailable",
        ),
    ],
)
async def test_run_detection_stream_rpc_error_handling(
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
    make_rpc_error: RpcErrorFactory,
    code: grpc.StatusCode,
    details: str,
    expects_error_callback: bool,
    expects_close: bool,
    expected_reason: str | None,
) -> None:
    """Stream RPC failures should either exit quietly or surface classified errors."""

    stream_error = make_rpc_error(code, details)
    fake_onyx_stub.StreamDetections = Mock(
        return_value=_RaisingAsyncStreamCall(stream_error)
    )
    on_error = AsyncMock()
    mock_device.close = AsyncMock()  # type: ignore[method-assign]

    await mock_device._run_detection_stream(
        on_detection=lambda _d: None,
        from_seconds_ago=0,
        on_error=on_error,
    )

    if expects_error_callback:
        on_error.assert_awaited_once()
        await_args = on_error.await_args
        assert await_args is not None
        received_exc = await_args.args[0]
        assert isinstance(received_exc, OnyxPublicError)
        assert received_exc.reason == expected_reason
    else:
        on_error.assert_not_awaited()

    if expects_close:
        mock_device.close.assert_awaited_once()
    else:
        mock_device.close.assert_not_awaited()


async def test_run_detection_stream_clears_current_stream_task_when_finished(
    mock_device: AsyncOnyxDevice,
    fake_onyx_stub: MockOnyxStub,
) -> None:
    """Stream runner should clear the tracked task when its own task exits."""

    fake_onyx_stub.StreamDetections = Mock(return_value=_AsyncStreamCall([]))

    stream_task = asyncio.create_task(
        mock_device._run_detection_stream(
            on_detection=lambda _d: None,
            from_seconds_ago=0,
            on_error=None,
        )
    )
    mock_device._stream_task = stream_task

    await stream_task

    assert mock_device._stream_task is None


async def test_close_disconnects(
    device_factory: Callable[..., AsyncOnyxDevice],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """close() should call _disconnect()."""

    device = device_factory()
    disconnect_mock = AsyncMock()

    monkeypatch.setattr(device, "_disconnect", disconnect_mock)

    await device.close()

    disconnect_mock.assert_awaited_once()


async def test_call_callback_supports_sync_and_async_callbacks(
    device_factory: Callable[..., AsyncOnyxDevice],
) -> None:
    """_call_callback() should execute sync callbacks and await async callbacks."""

    device = device_factory()
    seen: list[str] = []
    error_one = ConnectError("one")
    error_two = ConnectError("two")

    def sync_callback(value: OnyxPublicError) -> None:
        seen.append(str(value))

    async def async_callback(value: OnyxPublicError) -> None:
        seen.append(str(value))

    await device._call_callback(sync_callback, error_one)
    await device._call_callback(async_callback, error_two)

    assert seen == ["one", "two"]


async def test_disconnect_resets_state_and_closes_channel(
    mock_device: AsyncOnyxDevice,
    fake_channel: FakeChannel,
) -> None:
    """_disconnect() should clear connection state and close active channel."""

    await mock_device._disconnect()

    assert mock_device.connected is False
    assert mock_device._stub is None
    assert mock_device._channel is None
    fake_channel.close.assert_awaited_once()
