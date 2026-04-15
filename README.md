# onyxpublic

Python client library for Sintela Onyx gRPC APIs.

The package currently exposes:

- `AsyncOnyxDevice` for connecting to a single device, fetching identification, reading detections, reading system events, and running a background detection stream.
- Pydantic models such as `Detection` for working with normalized response payloads.

## Requirements

- Python 3.11+
- Access to an Onyx device endpoint
- A bearer token

## Install

Install the package from the repository root:

```bash
pip install .
```

For local development:

```bash
pip install -e .
```

## Quick Start

Use `AsyncOnyxDevice` when you want one object representing a single Onyx system.

```python
import asyncio
from datetime import datetime, timedelta, timezone

from onyxpublic import AsyncOnyxDevice
from onyxpublic.errors import OnyxPublicError


async def on_detection(detection) -> None:
    print(f"Detection {detection.id}: {detection.classification}")


async def on_stream_error(exc: OnyxPublicError) -> None:
    print(type(exc).__name__, exc.reason, exc.message)


async def main() -> None:
    device = AsyncOnyxDevice(
        "YOUR_TOKEN",
        host="127.0.0.1",
        port=8181,
        using_tls=True,
        # server_cert_path="certs/ca.crt",  # Optional custom CA bundle
    )

    try:
        await device.connect()

        if device.identity is not None:
            print("Connected to serial:", device.identity.serial_number)

        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        detections = await device.get_detections(from_time=one_hour_ago)
        print(f"Fetched {len(detections)} detections")

        system_events = await device.get_system_events()
        print(f"Fetched {len(system_events)} system events")

        # Starts a background task immediately. This call is not awaited.
        device.start_detection_stream(
            on_detection=on_detection,
            on_error=on_stream_error,
            from_seconds_ago=30,
        )

        await asyncio.sleep(60)
    finally:
        await device.close()


if __name__ == "__main__":
    asyncio.run(main())
```

An end-to-end sample is also available in `example.py`.

## Connection Behavior

- `connect()` establishes the gRPC channel and immediately validates connectivity with `GetIdentification`.
- `start_detection_stream(...)` is non-blocking and creates a background task. Do not `await` it.
- `close()` closes the device channel.
- If a unary RPC or detection stream hits a transport-level failure, the library classifies the gRPC error into a stable exception type and resets device state when appropriate. Reconnect explicitly before issuing more calls.

## Models

The high-level device API returns Pydantic models from `onyxpublic.model`.

- `OnyxIdentification` contains manufacturer, model, serial number, and fiber metadata.
- `Detection` contains normalized detection fields such as timestamps, classification, severity, and position information.
- `SystemEvent` contains normalized system event fields including level, status, timestamps, and descriptive metadata.

Enum-like protobuf values are normalized during model validation. Detection severity is parsed from enum names, while system event level and status accept enum names or integer values.

## Error Handling

The library exposes structured exceptions in `onyxpublic.errors`:

- `OnyxPublicError`: Base class for library errors. Includes `message`, `code`, `reason`, and `details` fields.
- `AuthError`: Raised when the server rejects credentials or authorization.
- `ConnectError`: Raised for transport-level connection failures. Inspect `reason` for values such as `timeout`, `connection_refused`, or `transport_unavailable`.
- `DeviceNotConnectedError`: Raised when an operation requires a connected device.
- `EventStreamerAlreadyRunningError`: Raised when a second detection stream is started while one is still active.
- `EventStreamerConnectionError`: Raised for non-auth, non-transport gRPC failures.

Typical handling pattern:

```python
from onyxpublic.errors import AuthError, ConnectError, OnyxPublicError


try:
    await device.connect()
except AuthError:
    ...
except ConnectError as exc:
    print(exc.reason)
except OnyxPublicError as exc:
    print(exc.message)
```

## TLS and Authentication

- A bearer token is always required.
- `using_tls=True` is the default and uses system CAs unless you provide `server_cert_path`.
- When `using_tls=True`, the client sends the token using gRPC call credentials.
- When `using_tls=False`, the device API attaches the token as request metadata on individual calls.

## Notes

- `from_time` passed to `get_detections()` must be timezone-aware.
- `device.identity` is populated after a successful `connect()`.
- `device.is_streaming` reports whether the background detection stream task is still active.

## Generated Code

This repository includes generated protobuf and gRPC files under `src/onyxpublic/api` and `src/onyxpublic/common`.

To regenerate them:

- Windows: `./scripts/codegen.ps1`
- Linux/macOS: `./scripts/codegen.sh`

The generation scripts also patch generated imports so both runtime files and `.pyi` stubs use package-qualified imports such as `from onyxpublic.api import onyx_pb2` and `from onyxpublic.common import common_pb2`.

See `scripts/README.md` for regeneration prerequisites.
