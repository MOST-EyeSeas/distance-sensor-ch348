#!/usr/bin/env python3
import argparse
import json
import socket


def parse_args():
    parser = argparse.ArgumentParser(
        description="Receive and print CH348 distance-sensor UDP JSON telemetry."
    )
    parser.add_argument("--host", default="0.0.0.0", help="Local UDP bind host.")
    parser.add_argument("--port", type=int, default=5005, help="Local UDP bind port.")
    parser.add_argument(
        "--warn-after",
        type=float,
        default=5.0,
        help="Warn when no packets arrive for this many seconds. Use 0 to disable.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    if args.warn_after > 0:
        sock.settimeout(args.warn_after)

    print(f"Listening for UDP telemetry on {args.host}:{args.port}", flush=True)

    while True:
        try:
            data, addr = sock.recvfrom(65535)
        except socket.timeout:
            print(f"No packets received for {args.warn_after:.1f}s", flush=True)
            continue
        except KeyboardInterrupt:
            print("Stopping UDP receiver.", flush=True)
            break

        text = data.decode("utf-8", errors="replace")
        try:
            message = json.loads(text)
            print(f"{addr[0]}:{addr[1]} {json.dumps(message, sort_keys=True)}", flush=True)
        except json.JSONDecodeError:
            print(f"{addr[0]}:{addr[1]} non-JSON payload: {text}", flush=True)

    sock.close()


if __name__ == "__main__":
    main()
