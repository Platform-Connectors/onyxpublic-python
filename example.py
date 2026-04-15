"""Async example for receiving Onyx detection events via AsyncOnyxDevice."""

import asyncio
import os
import signal
from contextlib import suppress

from dotenv import load_dotenv

from onyxpublic import AsyncOnyxDevice, Detection

# Load environment variables from .env file
load_dotenv()

HOST = os.getenv("ONYX_HOST", "127.0.0.1")
PORT = int(os.getenv("ONYX_PORT", "8181"))
TOKEN = os.getenv("ONYX_TOKEN", "")
USING_TLS = os.getenv("ONYX_TLS", "False").lower() == "true"


async def handle_detection(detection: Detection) -> None:
    """Convert protobuf detections to plain dicts before handling/printing."""
    print(detection)


def print_exception_details(prefix: str, exc: Exception) -> None:
    """Print a compact exception summary with the exception type."""
    code = getattr(exc, "code", None)
    reason = getattr(exc, "reason", None)
    message = getattr(exc, "message", str(exc))
    exc_type = type(exc).__name__

    cause_parts = [part for part in (reason, code) if part]
    cause_text = f" [{'/'.join(cause_parts)}]" if cause_parts else ""
    print(f"{prefix} {exc_type}{cause_text}: {message}")


async def handle_stream_error(exc: Exception) -> None:
    """Example error callback that simply prints the received error."""
    print_exception_details("Stream error:", exc)


async def main() -> None:
    """Main entry point to connect to onyx device."""
    device = AsyncOnyxDevice(
        TOKEN,
        host=HOST,
        port=PORT,
        using_tls=USING_TLS,
    )

    await device.connect()

    if device.identity is not None:
        print("Connected device serial:", device.identity.serial_number)

    # Call system_events and print them inside main
    system_events = await device.get_system_events()
    print(f"Current system events: {len(system_events)}")
    for event in system_events:
        print(f"- {event}")

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    # Graceful shutdown via Ctrl+C / SIGTERM (Unix; SIGTERM not available on some Windows setups).
    for sig_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    # Create a stream task
    device.start_detection_stream(
        on_detection=handle_detection,
        on_error=handle_stream_error,
    )

    stop_wait_task = asyncio.create_task(stop_event.wait(), name="onyx-stop-wait")

    try:
        # Run the rest of your asyncio app here.
        # Example: await app_server.serve()
        while not stop_event.is_set():
            if not device.is_streaming:
                break
            await asyncio.sleep(0.1)
    finally:
        await device.close()
        stop_event.set()
        stop_wait_task.cancel()
        with suppress(asyncio.CancelledError):
            await stop_wait_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print_exception_details("Stream exited with error:", exc)
        raise SystemExit(1) from exc
