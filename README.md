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

from onyxpublic import AsyncOnyxDevice


async def on_detection(detection):
	print(detection.id)


async def on_stream_error(exc):
	print("Stream error:", exc)


async def main() -> None:
	device = AsyncOnyxDevice(
		host="127.0.0.1",
		port=8181,
		using_tls=True,
		bearer_token="YOUR_TOKEN",
	)

	await device.connect()
	if device.identity is not None:
		print("Connected to serial:", device.identity.serial_number)

	# Starts streaming in the background and returns without blocking.
	# Ensure connect() has completed successfully before starting the stream.
	await device.start_detection_stream(
		on_detection=on_detection,
		from_seconds_ago=30,
		on_error=on_stream_error,
	)

	try:
		await asyncio.sleep(60)
	finally:
		await device.close()


if __name__ == "__main__":
	asyncio.run(main())
```

Streaming lifecycle notes:

- `start_detection_stream(...)` is non-blocking and runs work in a background task.
- Call `close()` to stop the stream and disconnect.
- If the stream disconnects due to a connection issue, `on_error` is called (if provided)
  and the device closes internally. Call `connect()` again, then start a new stream.
