#!/usr/bin/env python3
import argparse
import json
import socket
import threading
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


class SequenceCounter:
    def __init__(self):
        self._seq = 0
        self._lock = threading.Lock()

    def next(self) -> int:
        with self._lock:
            self._seq += 1
            return self._seq


def parse_args():
    parser = argparse.ArgumentParser(
        description="Read CH348 distance sensors and send JSON UDP telemetry."
    )
    parser.add_argument("--host", required=True, help="UDP target host or IP address.")
    parser.add_argument("--port", type=int, default=5005, help="UDP target port.")
    parser.add_argument(
        "--mode",
        choices=("sequential", "simultaneous"),
        default="sequential",
        help="Polling mode. Sequential polls sensors one after another; simultaneous uses one worker thread per sensor.",
    )
    parser.add_argument(
        "--rate-hz",
        type=float,
        default=5.0,
        help="Compatibility default for sequential full-array poll rate. Ignored when --poll-interval is set.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=None,
        help="Sequential mode sleep in seconds between sensor polls. Use 0 for max sequential speed.",
    )
    parser.add_argument(
        "--sensor-period",
        type=float,
        default=0.2,
        help="Simultaneous mode sleep in seconds between polls for each sensor. Use 0 for max per-sensor speed.",
    )
    parser.add_argument(
        "--read-timeout",
        type=float,
        default=0.2,
        help="Serial response timeout in seconds. Use 0 for blocking waits; positive values use a finite timeout.",
    )
    parser.add_argument(
        "--print-local",
        action="store_true",
        help="Also print each UDP JSON datagram locally.",
    )
    args = parser.parse_args()
    validate_nonnegative("--read-timeout", args.read_timeout)
    validate_nonnegative("--sensor-period", args.sensor_period)
    if args.poll_interval is not None:
        validate_nonnegative("--poll-interval", args.poll_interval)
    if args.rate_hz <= 0:
        raise ValueError("--rate-hz must be greater than 0")
    return args


def validate_nonnegative(name: str, value: float):
    if value < 0:
        raise ValueError(f"{name} must be non-negative")


def serial_timeout(read_timeout: float):
    return None if read_timeout == 0 else read_timeout


def open_sensor(sensor: SensorState, read_timeout: float) -> bool:
    if sensor.serial_port and sensor.serial_port.is_open:
        return True

    try:
        timeout = serial_timeout(read_timeout)
        sensor.serial_port = serial.Serial(
            sensor.port,
            baudrate=BAUDRATE,
            timeout=timeout,
            write_timeout=timeout,
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

    ser = sensor.serial_port
    try:
        if hasattr(ser, "cancel_read"):
            ser.cancel_read()
    except (OSError, serial.SerialException):
        pass

    try:
        ser.close()
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
        deadline = None if ser.timeout is None else time.monotonic() + ser.timeout
        while start and start[0] != 0xFF:
            if deadline is not None and time.monotonic() >= deadline:
                return None, False, "missing start byte"
            start = ser.read(1)

        if not start:
            return None, False, "no response"

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


def send_payload(sock: socket.socket, target, payload, print_local: bool, print_lock):
    line = json.dumps(payload, separators=(",", ":"))
    sock.sendto(line.encode("utf-8"), target)
    if print_local:
        with print_lock:
            print(line, flush=True)


def poll_once(sensor, args, sock, target, seq_counter, print_lock):
    seq = seq_counter.next()
    if not open_sensor(sensor, args.read_timeout):
        payload = make_payload(seq, sensor, None, False, "failed to open serial port")
        send_payload(sock, target, payload, args.print_local, print_lock)
        return

    distance_mm, checksum_ok, error = read_distance(sensor)
    payload = make_payload(seq, sensor, distance_mm, checksum_ok, error)
    send_payload(sock, target, payload, args.print_local, print_lock)


def run_sequential(args, sensors, sock, target, seq_counter, print_lock):
    if args.poll_interval is None:
        full_cycle_period = 1.0 / args.rate_hz
        sensor_interval = None
        print(f"Sequential mode: full-array rate {args.rate_hz:.3f} Hz", flush=True)
    else:
        full_cycle_period = None
        sensor_interval = args.poll_interval
        print(
            f"Sequential mode: sensor-to-sensor interval {sensor_interval:.3f}s",
            flush=True,
        )

    while True:
        cycle_start = time.monotonic()

        for index, sensor in enumerate(sensors):
            poll_once(sensor, args, sock, target, seq_counter, print_lock)
            if sensor_interval is not None and sensor_interval > 0:
                if index < len(sensors) - 1:
                    time.sleep(sensor_interval)

        if full_cycle_period is not None:
            sleep_time = full_cycle_period - (time.monotonic() - cycle_start)
            if sleep_time > 0:
                time.sleep(sleep_time)


def sensor_worker(sensor, args, sock, target, seq_counter, print_lock, stop_event):
    try:
        while not stop_event.is_set():
            poll_once(sensor, args, sock, target, seq_counter, print_lock)
            if args.sensor_period > 0:
                stop_event.wait(args.sensor_period)
    except Exception as exc:
        payload = make_payload(
            seq_counter.next(),
            sensor,
            None,
            False,
            f"worker error: {exc}",
        )
        send_payload(sock, target, payload, args.print_local, print_lock)
    finally:
        close_sensor(sensor)


def run_simultaneous(args, sensors, sock, target, seq_counter, print_lock):
    print(
        f"Simultaneous mode: per-sensor period {args.sensor_period:.3f}s",
        flush=True,
    )
    stop_event = threading.Event()
    threads = [
        threading.Thread(
            target=sensor_worker,
            args=(sensor, args, sock, target, seq_counter, print_lock, stop_event),
            name=f"distance_udp_{sensor.name}",
            daemon=True,
        )
        for sensor in sensors
    ]

    for thread in threads:
        thread.start()

    try:
        while any(thread.is_alive() for thread in threads):
            time.sleep(0.2)
    except KeyboardInterrupt:
        print("Stopping UDP telemetry.", flush=True)
        stop_event.set()
        for sensor in sensors:
            close_sensor(sensor)
    finally:
        stop_event.set()
        for sensor in sensors:
            close_sensor(sensor)
        for thread in threads:
            thread.join(timeout=2.0)


def main():
    args = parse_args()

    sensors = [SensorState(name, port) for name, port in SENSORS]
    target = (args.host, args.port)
    seq_counter = SequenceCounter()
    print_lock = threading.Lock()

    print(
        f"Sending CH348 distance telemetry to {args.host}:{args.port} "
        f"with read_timeout={serial_timeout(args.read_timeout)}",
        flush=True,
    )

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if args.mode == "sequential":
            run_sequential(args, sensors, sock, target, seq_counter, print_lock)
        else:
            run_simultaneous(args, sensors, sock, target, seq_counter, print_lock)

    except KeyboardInterrupt:
        print("Stopping UDP telemetry.", flush=True)
    finally:
        for sensor in sensors:
            close_sensor(sensor)
        sock.close()


if __name__ == "__main__":
    main()
