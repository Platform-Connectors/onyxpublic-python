# onyxpublic

Python API and CLI tools for Sintela Onyx protobuf/MTLV handling.

## Install (editable)

From this folder:

pip install -e .

## CLI examples

onyx-getidentification --address 127.0.0.1 --port 8181 --token YOUR_TOKEN --usingtls true
onyx-protoreader --input test.pb
onyx-streamexample --address 127.0.0.1 --port 8181 --token YOUR_TOKEN --usingtls true --sourceNamespace /grpcTimeseriesStreamOut

## Async device usage

Use `AsyncOnyxDevice` when you want one object representing a single Onyx system.

```python
import asyncio
from datetime import datetime, timedelta, timezone

from onyxpublic import AsyncOnyxDevice


async def on_detection(detection):
	# detection is a pydantic model with rich fields
	print(f"Detection {detection.id} at {detection.timestamp}")


async def on_stream_error(exc):
	print("Stream error:", exc)


async def main() -> None:
	# bearer_token is a positional argument.
	# host and port are keyword-only.
	device = AsyncOnyxDevice(
		"YOUR_TOKEN",
		host="127.0.0.1",
		port=8181,
		using_tls=True,
		# server_cert_path="path/to/cert.pem"  # Optional: custom CA certificate
	)

	try:
		await device.connect()
		if device.identity is not None:
			print("Connected to serial:", device.identity.serial_number)

		# 1. Unary methods (one-shot requests)
		# Get detections from the last hour. Note: datetime must be timezone-aware.
		one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
		detections = await device.get_detections(from_time=one_hour_ago)
		print(f"Found {len(detections)} recent detections")

		# 2. Streaming (background task)
		# Starts streaming in the background and returns without blocking.
		# Ensure connect() has completed successfully before starting the stream.
		await device.start_detection_stream(
			on_detection=on_detection,
			from_seconds_ago=30,
			on_error=on_stream_error,
		)

		await asyncio.sleep(60)
	finally:
		await device.close()


if __name__ == "__main__":
	asyncio.run(main())
```

### Error Handling

The library provides structured exceptions in `onyxpublic.errors`:

- `OnyxDeviceNotConnectedError`: Raised when calling methods before `connect()`.
- `EventStreamerAlreadyRunningError`: Raised if `start_detection_stream` is called while a stream is already active.
- `EventStreamerConnectionError`: Raised when the background stream fails (wraps gRPC errors).
- `OnyxPublicError`: Base class for all library exceptions.

### Important Notes

- **Timezones**: All `datetime` objects passed to the API (e.g., in `get_detections`) **must** be timezone-aware.
- **TLS Configuration**: Use `using_tls=True` (default) for encrypted connections. If using a self-signed or internal CA, provide the path via `server_cert_path`.

Streaming lifecycle notes:

- `start_detection_stream(...)` is non-blocking and runs work in a background task.
- Call `close()` to stop the stream and disconnect.
- If the stream disconnects due to a connection issue, `on_error` is called (if provided)
  and the device closes internally. Call `connect()` again, then start a new stream.
