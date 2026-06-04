#!/usr/bin/env python3
import argparse
import json
import socket
import time
from dataclasses import dataclass
from typing import Optional

import serial


COMMAND_BYTE = 0x55
BAUDRATE = 115200

SENSORS = (
    ("front_right", "/dev/ttyCH9344USB7"),
    ("front_left", "/dev/ttyCH9344USB6"),
    ("diag_down_45", "/dev/ttyCH9344USB5"),
    ("bottom_down_90", "/dev/ttyCH9344USB4"),
)


@dataclass
class SensorState:
    name: str
    port: str
    serial_port: Optional[serial.Serial] = None


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read CH348 distance sensors and send JSON UDP telemetry."
    )
    parser.add_argument("--host", required=True, help="UDP target host or IP address.")
    parser.add_argument("--port", type=int, default=5005, help="UDP target port.")
    parser.add_argument(
        "--rate-hz",
        type=float,
        default=5.0,
        help="Sequential full-array poll rate in Hz. Ignored when --poll-interval is set.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Seconds between full-array polling cycles.",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=0.2,
        help="Serial response timeout per sensor in seconds.",
    )
    parser.add_argument(
        "--print-local",
        action="store_true",
        help="Also print each UDP JSON datagram locally.",
    )
    return parser.parse_args()


def open_sensor(sensor: SensorState, read_timeout: float) -> bool:
    if sensor.serial_port and sensor.serial_port.is_open:
        return True

    try:
        sensor.serial_port = serial.Serial(
            sensor.port,
            baudrate=BAUDRATE,
            timeout=read_timeout,
            write_timeout=read_timeout,
        )
        sensor.serial_port.reset_input_buffer()
        return True
    except serial.SerialException as exc:
        sensor.serial_port = None
        print(f"{sensor.name} ({sensor.port}) unavailable: {exc}", flush=True)
        return False


def close_sensor(sensor: SensorState):
    if not sensor.serial_port:
        return

    try:
        sensor.serial_port.close()
    except serial.SerialException:
        pass
    finally:
        sensor.serial_port = None


def read_distance(sensor: SensorState):
    ser = sensor.serial_port
    if ser is None or not ser.is_open:
        return None, False, "serial port is not open"

    try:
        ser.reset_input_buffer()
        ser.write(bytes([COMMAND_BYTE]))
        ser.flush()

        start = ser.read(1)
        deadline = time.monotonic() + ser.timeout
        while start and start[0] != 0xFF and time.monotonic() < deadline:
            start = ser.read(1)

        if not start:
            return None, False, "no response"
        if start[0] != 0xFF:
            return None, False, "missing start byte"

        tail = ser.read(3)
        if len(tail) != 3:
            return None, False, "incomplete response"

        packet = bytes([start[0]]) + tail
        checksum = (packet[0] + packet[1] + packet[2]) & 0xFF
        checksum_ok = packet[3] == checksum
        if not checksum_ok:
            return None, False, f"checksum mismatch expected {checksum} got {packet[3]}"

        distance_mm = (packet[1] << 8) + packet[2]
        return distance_mm, True, None
    except serial.SerialException as exc:
        close_sensor(sensor)
        return None, False, str(exc)


def make_payload(seq: int, sensor: SensorState, distance_mm, checksum_ok: bool, error):
    valid = distance_mm is not None and checksum_ok
    payload = {
        "stamp": time.time(),
        "seq": seq,
        "sensor": sensor.name,
        "port": sensor.port,
        "distance_mm": distance_mm,
        "valid": valid,
        "checksum_ok": checksum_ok,
    }
    if error:
        payload["error"] = error
    return payload


def send_payload(sock: socket.socket, target, payload, print_local: bool):
    line = json.dumps(payload, separators=(",", ":"))
    sock.sendto(line.encode("utf-8"), target)
    if print_local:
        print(line, flush=True)


def main():
    args = parse_args()
    if args.poll_interval is not None:
        poll_interval = args.poll_interval
    else:
        if args.rate_hz <= 0:
            raise ValueError("--rate-hz must be greater than 0")
        poll_interval = 1.0 / args.rate_hz

    if poll_interval < 0:
        raise ValueError("--poll-interval must be non-negative")

    sensors = [SensorState(name, port) for name, port in SENSORS]
    target = (args.host, args.port)
    seq = 0

    print(
        f"Sending CH348 distance telemetry to {args.host}:{args.port} "
        f"every {poll_interval:.3f}s",
        flush=True,
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        while True:
            cycle_start = time.monotonic()

            for sensor in sensors:
                seq += 1
                if not open_sensor(sensor, args.read_timeout):
                    payload = make_payload(
                        seq, sensor, None, False, "failed to open serial port"
                    )
                    send_payload(sock, target, payload, args.print_local)
                    continue

                distance_mm, checksum_ok, error = read_distance(sensor)
                payload = make_payload(seq, sensor, distance_mm, checksum_ok, error)
                send_payload(sock, target, payload, args.print_local)

            elapsed = time.monotonic() - cycle_start
            sleep_time = poll_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("Stopping UDP telemetry.", flush=True)
    finally:
        for sensor in sensors:
            close_sensor(sensor)
        sock.close()


if __name__ == "__main__":
    main()
