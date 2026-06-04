#!/usr/bin/env bash
set -euo pipefail

usage() {
    echo "Usage: $0 <host> [port] [extra main_udp.py args...]"
    echo "       UDP_HOST=<host> UDP_PORT=5005 $0"
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    usage
    exit 0
fi

HOST="${1:-${UDP_HOST:-}}"
PORT="${2:-${UDP_PORT:-5005}}"

if [[ -z "${HOST}" ]]; then
    usage
    exit 2
fi

if [[ $# -gt 0 ]]; then
    shift
fi
if [[ $# -gt 0 ]]; then
    shift
fi

docker run --rm -it \
    -v "$(pwd)":/workspaces \
    --net=host \
    --privileged \
    --volume=/dev:/dev \
    --volume=/lib/modules:/lib/modules \
    --volume=/sys:/sys \
    distance-sensor \
    python3 /workspaces/scripts/main_udp.py --host "${HOST}" --port "${PORT}" "$@"
