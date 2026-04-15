"""Shared exceptions and gRPC error classification helpers for onyxpublic."""

from __future__ import annotations

import grpc

CONNECTION_REFUSED_DETAIL_MARKERS: tuple[str, ...] = (
    "connection refused",
    "actively refused",
    "10061",
)

AUTHENTICATION_GRPC_STATUS_CODES: frozenset[grpc.StatusCode] = frozenset(
    {
        grpc.StatusCode.PERMISSION_DENIED,
        grpc.StatusCode.UNAUTHENTICATED,
    }
)

TIMEOUT_DETAIL_MARKERS: tuple[str, ...] = (
    "deadline exceeded",
    "timed out",
    "timeout",
)

CONNECTION_RESET_REASONS: frozenset[str] = frozenset(
    {
        "timeout",
        "connection_refused",
        "transport_unavailable",
        "grpc_error",
    }
)

CONNECT_ERROR_REASONS: frozenset[str] = frozenset(
    {
        "timeout",
        "connection_refused",
        "transport_unavailable",
    }
)


class OnyxPublicError(Exception):
    """Base exception for this library."""

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        reason: str | None = None,
        details: str | None = None,
    ) -> None:
        """Initialize a library error with structured fields.

        Args:
            message: Short human-readable summary.
            code: Optional machine-friendly error code.
            reason: Optional normalized root cause label.
            details: Optional verbose context for debugging.
        """
        self.code = code
        self.reason = reason
        self.message = message
        self.details = details
        super().__init__(message)


class EventStreamerAlreadyRunningError(OnyxPublicError, RuntimeError):
    """Raised when start/connect is called while a streamer is already running."""


class EventStreamerStoppedError(OnyxPublicError, RuntimeError):
    """Raised when a stop request interrupts connection setup."""


class EventStreamerConnectionError(OnyxPublicError, RuntimeError):
    """Raised when connection setup fails without a terminal gRPC error."""


class AuthError(OnyxPublicError, PermissionError):
    """Raised when the server rejects credentials or authorization."""


class ConnectError(OnyxPublicError, ConnectionError):
    """Raised for transport-level device connection failures.

    Inspect ``reason`` to distinguish specific cases such as timeout,
    connection_refused, and transport_unavailable.
    """


class DeviceNotConnectedError(OnyxPublicError, RuntimeError):
    """Raised when an operation requires a connected device."""


def _error_text(exc: grpc.aio.AioRpcError) -> str:
    details = (exc.details() or "").lower()
    debug = (getattr(exc, "debug_error_string", lambda: "")() or "").lower()
    return f"{details} {debug}"


def _grpc_error_parts(
    operation: str,
    exc: grpc.aio.AioRpcError,
) -> tuple[str, str, str]:
    code = exc.code().name
    message = f"{operation} failed"
    details = exc.details() or "unknown gRPC error"
    return code, message, details


def _classify_reason(exc: grpc.aio.AioRpcError, combined: str) -> str:
    if exc.code() in AUTHENTICATION_GRPC_STATUS_CODES:
        return "authentication"
    if exc.code() is grpc.StatusCode.DEADLINE_EXCEEDED or any(
        marker in combined for marker in TIMEOUT_DETAIL_MARKERS
    ):
        return "timeout"
    if any(marker in combined for marker in CONNECTION_REFUSED_DETAIL_MARKERS):
        return "connection_refused"
    if exc.code() is grpc.StatusCode.UNAVAILABLE:
        return "transport_unavailable"
    return "grpc_error"


def classify_grpc_connection_error(
    exc: grpc.aio.AioRpcError,
    *,
    operation: str,
) -> OnyxPublicError:
    """Map connection/setup gRPC failures to stable library exceptions."""
    combined = _error_text(exc)
    reason = _classify_reason(exc, combined)
    code, message, details = _grpc_error_parts(operation, exc)

    if exc.code() in AUTHENTICATION_GRPC_STATUS_CODES:
        return AuthError(
            message,
            code=code,
            reason=reason,
            details=details,
        )
    if reason in CONNECT_ERROR_REASONS:
        return ConnectError(
            message,
            code=code,
            reason=reason,
            details=details,
        )
    return EventStreamerConnectionError(
        message,
        code=code,
        reason=reason,
        details=details,
    )


def should_reset_connection(error: OnyxPublicError) -> bool:
    """Return True when an RPC error should force a connection reset."""
    return error.reason in CONNECTION_RESET_REASONS


def classify_grpc_connection_error_with_reset(
    exc: grpc.aio.AioRpcError,
    *,
    operation: str,
) -> tuple[OnyxPublicError, bool]:
    """Classify an RPC failure and indicate whether connection reset is needed."""
    error = classify_grpc_connection_error(exc, operation=operation)
    return error, should_reset_connection(error)
