"""Transmit test bytes from Raspberry Pi UART TX and verify them on RX."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import config


def main() -> int:
    try:
        import serial
    except ImportError as error:
        print(f"Missing test dependency: {error}", file=sys.stderr)
        return 1

    connection = config.MAVLINK_CONNECTION
    if not connection.startswith("/"):
        print(
            f"Loopback test needs a serial device, but config points to {connection!r}",
            file=sys.stderr,
        )
        return 1

    print("Raspberry Pi UART loopback test")
    print(f"Device: {connection} @ {config.MAVLINK_BAUD} baud")
    print("This sends test text from Pi TX; it sends no MAVLink or flight commands.")
    print("Disconnect the flight controller's signal wire before running this test.")

    try:
        with serial.Serial(
            connection,
            baudrate=config.MAVLINK_BAUD,
            timeout=1.0,
            write_timeout=1.0,
            exclusive=True,
        ) as port:
            for index in range(1, 6):
                sent = f"PI_UART_LOOPBACK_{index:02d}\r\n".encode("ascii")
                port.reset_input_buffer()
                port.write(sent)
                port.flush()
                received = port.read(len(sent))
                if received != sent:
                    print(
                        f"FAIL {index}/5: sent {sent!r}, received {received!r}",
                        file=sys.stderr,
                    )
                    print("Check the jumper between physical pins 8 and 10.")
                    return 1
                print(f"PASS {index}/5: received {received.decode('ascii').strip()}")
    except (OSError, ValueError) as error:
        print(f"Could not test {connection}: {error}", file=sys.stderr)
        return 1

    print("SUCCESS: Pi UART TX-to-RX loopback works.")
    print("This does not test MAVLink output or UART configuration on the flight controller.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
