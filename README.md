# CH348 Distance Sensor UDP Telemetry

This project reads four distance sensors connected through CH348 serial ports and sends the readings as UDP JSON telemetry. The current phase is UDP-only; it does not publish ROS2 topics and does not touch the vehicle ROS2/autonomy stack.

## Hardware Mapping

The current USB numbering is stable and used directly:

| Serial port | Sensor name |
| --- | --- |
| `/dev/ttyCH9344USB7` | `front_right` |
| `/dev/ttyCH9344USB6` | `front_left` |
| `/dev/ttyCH9344USB5` | `diag_down_45` |
| `/dev/ttyCH9344USB4` | `bottom_down_90` |

The sensor protocol uses baudrate `115200`, command byte `0x55`, and a 4-byte response: start byte `0xff`, high byte, low byte, checksum. Distance is decoded as `(high << 8) + low` in millimeters.

## UDP Packet Format

The sender emits one JSON datagram per sensor reading:

```json
{
  "stamp": 1780000000.123,
  "seq": 512,
  "sensor": "front_right",
  "port": "/dev/ttyCH9344USB7",
  "distance_mm": 1342,
  "valid": true,
  "checksum_ok": true
}
```

If a read fails, the datagram is still sent with `valid: false`, `distance_mm: null`, and an `error` string when available. This lets the receiver see per-sensor failures without stopping the whole telemetry path.

## Listen On The Laptop

From this repository:

```bash
python3 scripts/udp_receiver.py --port 5005
```

The receiver binds UDP port `5005` by default and prints decoded JSON packets. It warns when no packets arrive for a few seconds.

## Manual Sender

On the vehicle, from `/home/pi/proj/distance-sensor-ch348`:

```bash
./run_udp.sh 192.168.2.1 5005 --mode sequential --poll-interval 0.1 --read-timeout 0.05
```

`run_udp.sh` runs the existing `distance-sensor` Docker image with host networking, privileged access, and the required `/dev`, `/lib/modules`, and `/sys` mounts. It forwards any extra arguments to `scripts/main_udp.py`.

No Docker rebuild is required unless the `distance-sensor` base image is missing on the vehicle.

## Deploy And Control

From the laptop/dev environment, use:

```bash
scripts/deploy_distance_udp.sh --host 192.168.2.1 --restart --mode sequential --poll-interval 0.1 --read-timeout 0.05
```

Defaults:

- Vehicle SSH target: `pi@192.168.2.2`
- Password for `sshpass`, if available: `raspberry`
- Vehicle repo path: `/home/pi/proj/distance-sensor-ch348`
- Docker container name: `distance_udp`
- UDP port: `5005`

Deploy actions:

```bash
scripts/deploy_distance_udp.sh --host 192.168.2.1 --restart
scripts/deploy_distance_udp.sh --stop
scripts/deploy_distance_udp.sh --status
scripts/deploy_distance_udp.sh --logs
scripts/deploy_distance_udp.sh --follow-logs
scripts/deploy_distance_udp.sh --clean
```

Action behavior:

- `--restart` / `--start`: remove any old `distance_udp` container, then start a new detached container.
- `--stop`: run `docker stop distance_udp` and keep the stopped container for log inspection.
- `--status`: show `docker ps -a --filter name=distance_udp` plus the container state.
- `--logs`: show the last 100 Docker log lines.
- `--follow-logs`: follow Docker logs.
- `--clean`: run `docker rm -f distance_udp`.

The deploy script does not run `git pull` by default. Use `--pull` only when the vehicle has network access and you explicitly want `git pull --ff-only`.

## Sender Parameters

Useful `scripts/main_udp.py` parameters:

- `--host HOST`: UDP target host or IP. For the current laptop receiver, use `192.168.2.1`.
- `--port PORT`: UDP target port. Default is `5005`.
- `--mode sequential|simultaneous`: polling mode. Default is `sequential`.
- `--poll-interval SEC`: sequential-mode sleep between sensor polls. `--poll-interval 0` means max sequential polling speed.
- `--sensor-period SEC`: simultaneous-mode sleep between polls for each sensor. `--sensor-period 0` means max per-sensor polling speed.
- `--read-timeout SEC`: serial response timeout. `--read-timeout 0` means blocking serial read; positive values use a finite pyserial timeout.
- `--print-local`: also print each JSON datagram locally.

Avoid `--print-local` for long background deployments because every UDP packet is written into Docker logs and the log can grow quickly.

## Example Modes

Sequential default-style run:

```bash
scripts/deploy_distance_udp.sh --host 192.168.2.1 --restart --mode sequential --poll-interval 0.1 --read-timeout 0.05
```

Sequential max speed:

```bash
scripts/deploy_distance_udp.sh --host 192.168.2.1 --restart --mode sequential --poll-interval 0 --read-timeout 0
```

Simultaneous moderate:

```bash
scripts/deploy_distance_udp.sh --host 192.168.2.1 --restart --mode simultaneous --sensor-period 0.05 --read-timeout 0.02
```

Simultaneous max speed:

```bash
scripts/deploy_distance_udp.sh --host 192.168.2.1 --restart --mode simultaneous --sensor-period 0 --read-timeout 0
```

This phase intentionally stops at UDP telemetry. ROS2 publishing should be added in a later phase after the UDP helper scripts are tested.
