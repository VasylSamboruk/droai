"""Read-only raw UART and MAVLink monitor for Raspberry Pi."""

from __future__ import annotations

from collections import Counter
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config


def main() -> int:
    try:
        import serial
        from pymavlink.dialects.v20 import common as mavlink2
    except ImportError as error:
        print(f"Missing test dependency: {error}", file=sys.stderr)
        return 1

    connection = config.MAVLINK_CONNECTION
    if not connection.startswith("/"):
        print(
            f"UART test needs a serial device, but config points to {connection!r}",
            file=sys.stderr,
        )
        return 1

    print("Raw UART + MAVLink test (receive-only; sends no flight commands)")
    print(f"Link: {config.MAVLINK_CONNECTION} @ {config.MAVLINK_BAUD} baud")
    print(
        f"Watching RC channel {config.MAVLINK_TARGET_LOCK_CHANNEL} (lock) and "
        f"{config.MAVLINK_TARGET_CYCLE_CHANNEL} (next target)"
    )
    print("Stop main.py first. Press Ctrl+C to exit.\n", flush=True)

    port = None
    try:
        port = serial.Serial(
            connection,
            baudrate=config.MAVLINK_BAUD,
            timeout=0.25,
            exclusive=True,
        )
        parser = mavlink2.MAVLink(None)
        bytes_received = 0
        bad_frames = 0
        message_counts: Counter[str] = Counter()
        last_packet_at: float | None = None
        last_heartbeat_at: float | None = None
        last_rc_at: float | None = None
        rc_channels: dict[int, int | None] = {}
        last_raw_bytes = b""
        last_report_at = time.monotonic()
        reported_bytes = 0

        while True:
            chunk = port.read(512)
            if chunk:
                bytes_received += len(chunk)
                last_raw_bytes = chunk[-16:]
                for message in parser.parse_buffer(chunk) or []:
                    message_type = message.get_type()
                    if message_type == "BAD_DATA":
                        bad_frames += 1
                        continue

                    message_counts[message_type] += 1
                    last_packet_at = time.monotonic()
                    if message_type == "HEARTBEAT":
                        last_heartbeat_at = last_packet_at
                    elif message_type in {"RC_CHANNELS", "RC_CHANNELS_RAW"}:
                        last_rc_at = last_packet_at
                        for channel in range(1, 19):
                            field = f"chan{channel}_raw"
                            if hasattr(message, field):
                                value = int(getattr(message, field))
                                rc_channels[channel] = (
                                    value if 0 < value < 65535 else None
                                )

            now = time.monotonic()
            if now - last_report_at < 1.0:
                continue
            elapsed = now - last_report_at
            byte_rate = (bytes_received - reported_bytes) / elapsed
            last_report_at = now
            reported_bytes = bytes_received

            if bytes_received == 0:
                link_state = "NO UART BYTES"
            elif not message_counts:
                link_state = "BYTES RECEIVED, NO MAVLINK PACKETS"
            elif last_heartbeat_at is None or now - last_heartbeat_at > 3.0:
                link_state = "MAVLINK PACKETS, NO FRESH HEARTBEAT"
            else:
                link_state = "HEARTBEAT OK"

            lock_channel = config.MAVLINK_TARGET_LOCK_CHANNEL
            cycle_channel = config.MAVLINK_TARGET_CYCLE_CHANNEL
            heartbeat_age = (
                "none"
                if last_heartbeat_at is None
                else f"{now - last_heartbeat_at:.1f}s ago"
            )
            rc_age = None if last_rc_at is None else now - last_rc_at
            rc_message_age = "none" if rc_age is None else f"{rc_age:.1f}s ago"
            lock_value = rc_channels.get(lock_channel)
            cycle_value = rc_channels.get(cycle_channel)
            lock_state = (
                "NO DATA" if rc_age is None or rc_age > 2.0 or lock_value is None
                else f"{lock_value}us ({'ON' if lock_value > config.MAVLINK_RC_SWITCH_THRESHOLD_US else 'OFF'})"
            )
            cycle_state = (
                "NO DATA" if rc_age is None or rc_age > 2.0 or cycle_value is None
                else f"{cycle_value}us ({'ON' if cycle_value > config.MAVLINK_RC_SWITCH_THRESHOLD_US else 'OFF'})"
            )
            types = ", ".join(
                f"{name}:{count}" for name, count in sorted(message_counts.items())
            ) or "none"
            raw_sample = last_raw_bytes.hex(" ") if last_raw_bytes and not message_counts else "—"
            print(
                f"{link_state} | UART bytes: {bytes_received} "
                f"({byte_rate:.1f}/s) | MAVLink packets: {sum(message_counts.values())} "
                f"| parser bad frames: {bad_frames} | types: {types} | "
                f"heartbeat: {heartbeat_age} | RC msg: {rc_message_age} | "
                f"CH{lock_channel}: {lock_state} | CH{cycle_channel}: {cycle_state} | "
                f"raw: {raw_sample}",
                flush=True,
            )
    except (OSError, ValueError) as error:
        print(f"Could not read {connection}: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nTest stopped.")
        return 0
    finally:
        if port is not None and port.is_open:
            port.close()


if __name__ == "__main__":
    raise SystemExit(main())
