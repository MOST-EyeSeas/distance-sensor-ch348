#!/usr/bin/env bash
set -euo pipefail

SESSION_NAME="distance_udp"
DEFAULT_REPO="/home/pi/proj/distance-sensor-ch348"
DEFAULT_PORT="5005"
PIDFILE="/tmp/${SESSION_NAME}.pid"
LOGFILE="/tmp/${SESSION_NAME}.log"

usage() {
    cat <<USAGE
Usage:
  $0 --vehicle USER@HOST --host UDP_HOST [--port UDP_PORT] --restart [main_udp args]
  $0 --vehicle USER@HOST --stop
  $0 --vehicle USER@HOST --status

Actions:
  --start                 Stop any existing sender, then start a new sender.
  --restart              Stop any existing sender, then start a new sender.
  --stop                 Stop the remote sender.
  --status               Show remote sender status.

Options:
  --vehicle USER@HOST     SSH target for the vehicle.
  --repo PATH             Vehicle repository path. Default: ${DEFAULT_REPO}
  --host HOST             UDP destination host for run_udp.sh.
  --port PORT             UDP destination port. Default: ${DEFAULT_PORT}
  --mode MODE             Forwarded to main_udp.py: sequential or simultaneous.
  --poll-interval SEC     Forwarded to main_udp.py for sequential mode.
  --sensor-period SEC     Forwarded to main_udp.py for simultaneous mode.
  --read-timeout SEC      Forwarded to main_udp.py. Use 0 for blocking reads.
  --print-local           Forwarded to main_udp.py.
  --pull                  Run git pull --ff-only on the vehicle before start/restart.
  --                      Pass remaining arguments directly to main_udp.py.

Examples:
  $0 --vehicle pi@192.168.2.2 --host 192.168.2.1 --port 5005 --restart --mode sequential --poll-interval 0.1 --read-timeout 0.05 --print-local
  $0 --vehicle pi@192.168.2.2 --stop
  $0 --vehicle pi@192.168.2.2 --status
USAGE
}

require_value() {
    local option="$1"
    local value="${2:-}"
    if [[ -z "${value}" ]]; then
        echo "Missing value for ${option}" >&2
        exit 2
    fi
}

quote_words() {
    printf "%q " "$@"
}

VEHICLE=""
REPO="${DEFAULT_REPO}"
HOST=""
PORT="${DEFAULT_PORT}"
ACTION=""
PULL=0
RUN_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            usage
            exit 0
            ;;
        --vehicle)
            require_value "$1" "${2:-}"
            VEHICLE="$2"
            shift 2
            ;;
        --repo)
            require_value "$1" "${2:-}"
            REPO="$2"
            shift 2
            ;;
        --host)
            require_value "$1" "${2:-}"
            HOST="$2"
            shift 2
            ;;
        --port)
            require_value "$1" "${2:-}"
            PORT="$2"
            shift 2
            ;;
        --mode|--poll-interval|--sensor-period|--read-timeout)
            require_value "$1" "${2:-}"
            RUN_ARGS+=("$1" "$2")
            shift 2
            ;;
        --print-local)
            RUN_ARGS+=("$1")
            shift
            ;;
        --pull)
            PULL=1
            shift
            ;;
        --start|--restart|--stop|--status)
            if [[ -n "${ACTION}" ]]; then
                echo "Only one action may be specified." >&2
                exit 2
            fi
            ACTION="${1#--}"
            shift
            ;;
        --)
            shift
            RUN_ARGS+=("$@")
            break
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "${VEHICLE}" ]]; then
    echo "--vehicle is required." >&2
    exit 2
fi

if [[ -z "${ACTION}" ]]; then
    ACTION="restart"
fi

if [[ "${ACTION}" == "start" || "${ACTION}" == "restart" ]]; then
    if [[ -z "${HOST}" ]]; then
        echo "--host is required for ${ACTION}." >&2
        exit 2
    fi
fi

REMOTE_RUN_ARGS=("${HOST}" "${PORT}" "${RUN_ARGS[@]}")
RUN_CMD=$(quote_words "./run_udp.sh" "${REMOTE_RUN_ARGS[@]}")
REPO_Q=$(printf "%q" "${REPO}")
SESSION_Q=$(printf "%q" "${SESSION_NAME}")
PIDFILE_Q=$(printf "%q" "${PIDFILE}")
LOGFILE_Q=$(printf "%q" "${LOGFILE}")
RUN_CMD_Q=$(printf "%q" "${RUN_CMD}")
ACTION_Q=$(printf "%q" "${ACTION}")
PULL_Q=$(printf "%q" "${PULL}")

ssh "${VEHICLE}" \
    "REPO=${REPO_Q} SESSION=${SESSION_Q} PIDFILE=${PIDFILE_Q} LOGFILE=${LOGFILE_Q} RUN_CMD=${RUN_CMD_Q} ACTION=${ACTION_Q} PULL=${PULL_Q} bash -s" <<'REMOTE'
set -euo pipefail

stop_sender() {
    if command -v tmux >/dev/null 2>&1 && tmux has-session -t "${SESSION}" 2>/dev/null; then
        tmux kill-session -t "${SESSION}"
        echo "Stopped tmux session ${SESSION}."
    fi

    if [[ -f "${PIDFILE}" ]]; then
        pid="$(cat "${PIDFILE}")"
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            kill "${pid}" 2>/dev/null || true
            sleep 1
            kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null || true
            echo "Stopped nohup process ${pid}."
        fi
        rm -f "${PIDFILE}"
    fi
}

status_sender() {
    if command -v tmux >/dev/null 2>&1 && tmux has-session -t "${SESSION}" 2>/dev/null; then
        echo "running: tmux session ${SESSION}"
        tmux list-sessions | grep "^${SESSION}:"
        return 0
    fi

    if [[ -f "${PIDFILE}" ]]; then
        pid="$(cat "${PIDFILE}")"
        if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
            echo "running: nohup pid ${pid}"
            echo "log: ${LOGFILE}"
            return 0
        fi
        echo "stale pidfile: ${PIDFILE}"
        return 1
    fi

    echo "not running"
    return 1
}

start_sender() {
    cd "${REPO}"

    if [[ "${PULL}" == "1" ]]; then
        git pull --ff-only
    fi

    if command -v tmux >/dev/null 2>&1; then
        tmux new-session -d -s "${SESSION}" "cd \"${REPO}\" && exec ${RUN_CMD}"
        echo "Started tmux session ${SESSION}: ${RUN_CMD}"
    else
        nohup bash -lc "cd \"${REPO}\" && exec ${RUN_CMD}" > "${LOGFILE}" 2>&1 &
        echo "$!" > "${PIDFILE}"
        echo "Started nohup pid $(cat "${PIDFILE}"): ${RUN_CMD}"
        echo "log: ${LOGFILE}"
    fi
}

case "${ACTION}" in
    stop)
        stop_sender
        ;;
    status)
        status_sender
        ;;
    start|restart)
        stop_sender
        start_sender
        status_sender || true
        ;;
    *)
        echo "Unknown action: ${ACTION}" >&2
        exit 2
        ;;
esac
REMOTE
