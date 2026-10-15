# MAVLink telemetry and approach commands

This folder receives vehicle telemetry on a configured MAVLink link. Channel 8
still toggles the video target lock. While that lock is active, the main app can
also take flight control for visual approach, but command transmission is
disabled by default (`MAVLINK_APPROACH_TX=0`). Default `APPROACH_CONTROL_MODE=acro`
switches ACRO and streams `RC_CHANNELS_OVERRIDE` from the FIX PID (frame error →
sticks, optional RTL on RC loss). Set `guided` to keep SET_POSITION_TARGET_LOCAL_NED
velocity instead. The standalone `python -m mavlink.telemetry` monitor remains
receive-only and does not arm or change RC mapping.

## Configuration

Set these values in `config_mavlink.py` or through environment variables:

| Setting | Default | Purpose |
| --- | --- | --- |
| `MAVLINK_ENABLED` | `1` | Enable MAVLink reception in the app. |
| `MAVLINK_CONNECTION` | `/dev/ttyAMA0` on Raspberry Pi 5 GPIO14/15; `udpin:0.0.0.0:14550` on PC | Select the incoming MAVLink transport/endpoint. This is not an RC channel. |
| `MAVLINK_BAUD` | `57600` | UART/serial baud rate; ignored by UDP transports. Must match the flight-controller port. |
| `MAVLINK_HEARTBEAT_TIMEOUT` | `3.0` | Seconds before status reports a heartbeat as disconnected. |
| `MAVLINK_TARGET_LOCK_CHANNEL` | `8` | Hold switch: ON locks the target; OFF unlocks it. |
| `MAVLINK_APPROACH_TX` | `0` | Explicitly enable flight commands while lock + channel 8 are active. Leave `0` for lock/telemetry-only operation. |
| `APPROACH_CONTROL_MODE` | `acro` | `acro` = RC override + FIX PID; `guided` = body-NED velocity. |
| `APPROACH_ACRO_GEOMETRY` | `copter` | `copter` = camera forward; `rocket` = steep-dive FIX mapping. |
| `APPROACH_PITCH_COMPENSATION_ENABLED` | `0` | Opt-in fixed-camera pitch compensation; bench-calibrate before enabling. |
| `CAMERA_MOUNT_PITCH_DOWN_DEG` | `15` | Camera angle below the aircraft nose, used by the compensation model. |
| `FIX_ACRO_THROTTLE_US` | `1500` | ACRO throttle while closing, microseconds. |
| `FIX_RC_LOSS_FAILSAFE_ENABLED` | `1` | Send RTL if RC is lost during auto-approach. |
| `MAVLINK_APPROACH_REQUIRE_ARMED` | `1` | Do not take control until the vehicle is armed. |
| `MAVLINK_APPROACH_REQUIRE_FIX_MODE` | `1` | Fail closed unless fresh `RC_CHANNELS` confirms the configured FIX switch is ON. |
| `MAVLINK_APPROACH_RATE_HZ` | `10` | Setpoint stream rate. |
| `MAVLINK_APPROACH_GUIDED_MODE` | `4` | ArduCopter GUIDED custom mode. PX4 uses Offboard automatically. |
| `MAVLINK_APPROACH_HOLD_MODE` | `5` | Mode to restore if the previous mode is unknown (ArduCopter LOITER). |
| `MAVLINK_TARGET_CYCLE_CHANNEL` | `9` | RC channel used to cycle to the next locked target. |
| `MAVLINK_RC_SWITCH_THRESHOLD_US` | `1500` | RC PWM threshold separating switch-off and switch-on. |
| `MAVLINK_FIX_MODE_CHANNEL` | `0` | FIX interlock channel; `0` reuses the target-lock channel (8 by default). |
| `MAVLINK_FIX_MODE_PWM_US` | `0` | Expected FIX-on PWM; `0` treats values above `MAVLINK_RC_SWITCH_THRESHOLD_US` as ON. |
| `MAVLINK_FIX_MODE_PWM_TOLERANCE_US` | `100` | Allowed difference from the configured FIX PWM position. |

Examples for Windows PowerShell:

```powershell
# UDP listener, when the vehicle or a telemetry radio sends MAVLink to port 14550
$env:MAVLINK_ENABLED = "1"
$env:MAVLINK_CONNECTION = "udpin:0.0.0.0:14550"
python -m mavlink.telemetry
```

```powershell
# Serial telemetry receiver (use the COM port and baud configured for your link)
$env:MAVLINK_ENABLED = "1"
$env:MAVLINK_CONNECTION = "COM6"
$env:MAVLINK_BAUD = "57600"
python -m mavlink.telemetry
```

The sender/autopilot must already be configured to emit telemetry on the selected
link. The receiver does not request data streams, so it remains a listener.
Choose the connection string for the transport available on your bench; switching
`MAVLINK_CONNECTION` switches that input link. It does not select or change an
aircraft radio/RC channel. Start the main app with `MAVLINK_ENABLED=1` to use the
RC switch integration. A rising edge on channel 8 toggles the target lock just
like Q; a rising edge on channel 9 cycles to the next tracked target just like W.
The switch-on value is above `MAVLINK_RC_SWITCH_THRESHOLD_US`, and switch-off
must be at or below it. Each action occurs once per switch-on, not continuously
while the switch remains high.

### Raspberry Pi UART wiring

For receive-only RC switch testing, connect the flight controller UART `TX` to
Raspberry Pi `GPIO15/RXD` (physical pin 10), and connect the grounds (for example,
flight-controller `GND` to Pi physical pin 6). This is one UART link; the Pi RX
pin is the only signal pin needed to receive. Do not connect the Pi `5V` pin to
the flight controller UART. Confirm the controller's UART TX logic level is 3.3 V
before connecting directly; use a level shifter if it is 5 V. Enable the Pi
hardware serial port and disable its serial login console, then set
`MAVLINK_CONNECTION=/dev/ttyAMA0` for the Pi 5 GPIO14/15 UART and set
`MAVLINK_BAUD` to the flight-controller port's configured baud rate. On some
systems `/dev/serial0` may resolve to a different UART, so verify its target
before using it. Configure the flight-controller port to transmit MAVLink
messages including `RC_CHANNELS`. Leave `MAVLINK_APPROACH_TX=0` for lock-only
testing; the Crossfire receiver remains connected to and controls the flight
controller directly.

## Received status

The JSON status stream reports heartbeat age, system/component IDs, armed flag,
autopilot and vehicle type, custom mode number, GPS fix/position/altitude,
local NED position and velocity, velocity/heading, attitude, battery
voltage/remaining percentage, and the raw values from RC channels present in
the received message, plus the inferred FIX-switch position when both FIX
settings are configured. FIX state is derived from RC PWM, not the autopilot's
authoritative flight-mode state; stale RC data is treated as unknown.
Missing or unknown fields are `null`; stale heartbeat status is reported as
disconnected. Roll, pitch, and yaw are shown in the dashboard.
Custom flight-mode numbers are autopilot-specific and are not translated here.
Set `MAVLINK_FIX_MODE_CHANNEL` to the actual RC channel used for FIX and
`MAVLINK_FIX_MODE_PWM_US` to the PWM value that means FIX is ON. With the default
`MAVLINK_APPROACH_REQUIRE_FIX_MODE=1`, automatic commands are not sent unless
fresh RC telemetry confirms that switch is ON. The default channel/PWM values
are 0 (unconfigured), so configure them before expecting approach commands.

## Video lock controls

The dashboard's **Target lock** checkbox (T) enables or disables local visual
tracking. **Lock target** (Q) locks the highest-confidence detection or releases
the current lock; W cycles to another confirmed track ID. For browser webcam
input, the locked box is drawn red in the local video overlay. Channel 8 is a
hold switch: ON locks the target and, only with `MAVLINK_APPROACH_TX=1`, enables
the configured flight-control path; OFF unlocks it. Flight commands are disabled
by default. When explicitly enabled, commands are additionally gated by armed
state and (by default) a fresh, configured FIX switch reported in `RC_CHANNELS`.
This does not arm the vehicle. Releasing an RC override sends zero PWM values for the
override channels; `65535` is reserved for ignoring a channel, not releasing it.

## Standalone usage

`MAVLinkTelemetry` can also be used independently:

```python
from mavlink.telemetry import MAVLinkTelemetry

telemetry = MAVLinkTelemetry()
telemetry.connect()
telemetry.poll(timeout=1.0)
print(telemetry.status())
telemetry.close()
```

Call `close()` when the receiver is no longer needed. Dependency:
`pymavlink` (included in the project's `requirements.txt`).
