"""Shared pytest fixtures and typed test doubles for async device tests."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol
from unittest.mock import AsyncMock, Mock

import grpc
import pytest

from onyxpublic.api import onyx_pb2
from onyxpublic.common import common_pb2
from onyxpublic.device import AsyncOnyxDevice

from . import MOCK_DETECTION, MOCK_SYSTEM_EVENT


@pytest.fixture
def mock_detection() -> common_pb2.Detection:
    """Fixture providing a fresh clone of a standard mock Detection."""
    clone = common_pb2.Detection()
    clone.CopyFrom(MOCK_DETECTION)
    return clone


@pytest.fixture
def mock_system_event() -> onyx_pb2.SystemEvent:
    """Fixture providing a fresh clone of a standard mock SystemEvent."""
    clone = onyx_pb2.SystemEvent()
    clone.CopyFrom(MOCK_SYSTEM_EVENT)
    return clone


class FakeChannel:
    """Minimal async channel double exposing an awaitable close method."""

    def __init__(self) -> None:
        """Initialize the channel close mock used by shutdown assertions."""
        self.close = AsyncMock()


class MockOnyxStub:
    """Container for RPC method mocks used by AsyncOnyxDevice tests."""

    def __init__(self) -> None:
        """Create default mock methods for the unary and stream RPCs."""
        self.GetIdentification = AsyncMock()
        self.GetDetections = AsyncMock()
        self.GetSystemEvents = AsyncMock()
        self.StreamDetections = Mock()


class RpcErrorFactory(Protocol):
    """Callable protocol for building grpc.aio.AioRpcError test instances."""

    def __call__(
        self,
        code: grpc.StatusCode,
        details: str,
        debug: str = "",
    ) -> grpc.aio.AioRpcError: ...


@pytest.fixture
def fake_channel() -> FakeChannel:
    """Return a fresh fake async channel per test."""

    return FakeChannel()


@pytest.fixture
def fake_onyx_stub() -> MockOnyxStub:
    """Return a fresh typed stub double with mocked RPC methods."""

    return MockOnyxStub()


@pytest.fixture
def patched_onyx_stub(
    monkeypatch: pytest.MonkeyPatch,
    fake_channel: FakeChannel,
    fake_onyx_stub: MockOnyxStub,
) -> MockOnyxStub:
    """Patch device transport creation and return the patched stub mock.

    This fixture ensures AsyncOnyxDevice uses fake transport objects rather than
    creating real network channels/stubs during tests.
    """

    monkeypatch.setattr(
        "onyxpublic.device.create_async_client",
        lambda *args, **kwargs: fake_channel,
    )
    monkeypatch.setattr(
        "onyxpublic.device.onyx_pb2_grpc.OnyxStub",
        lambda *args, **kwargs: fake_onyx_stub,
    )
    return fake_onyx_stub


@pytest.fixture
def device_factory() -> Callable[..., AsyncOnyxDevice]:
    """Fixture providing a factory to create AsyncOnyxDevice instances with defaults."""

    def _create_device(**kwargs) -> AsyncOnyxDevice:
        return AsyncOnyxDevice(bearer_token="token", host="127.0.0.1", **kwargs)

    return _create_device


@pytest.fixture
def mock_device(
    device_factory: Callable[..., AsyncOnyxDevice],
    fake_channel: FakeChannel,
    fake_onyx_stub: MockOnyxStub,
) -> AsyncOnyxDevice:
    """Return an AsyncOnyxDevice test instance pre-marked as connected."""

    device = device_factory(using_tls=False)
    device._channel = fake_channel  # type: ignore[assignment]
    device._stub = fake_onyx_stub  # type: ignore[assignment]
    device._connected = True
    return device


@pytest.fixture
def make_rpc_error() -> RpcErrorFactory:
    """Provide a factory for creating deterministic grpc.aio.AioRpcError values."""

    def _factory(
        code: grpc.StatusCode,
        details: str,
        debug: str = "",
    ) -> grpc.aio.AioRpcError:
        """Build a gRPC async error instance with the supplied status and detail."""
        metadata = grpc.aio.Metadata()
        return grpc.aio.AioRpcError(code, metadata, metadata, details, debug)

    return _factory
