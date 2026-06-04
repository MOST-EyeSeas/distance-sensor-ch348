#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="distance_udp"
DEFAULT_VEHICLE="pi@192.168.2.2"
DEFAULT_PASSWORD="raspberry"
DEFAULT_REPO="/home/pi/proj/distance-sensor-ch348"
DEFAULT_PORT="5005"

usage() {
    cat <<USAGE
Usage:
  $0 --host UDP_HOST [--port UDP_PORT] --restart [main_udp args]
  $0 --stop
  $0 --status
  $0 --logs
  $0 --clean

Actions:
  --start                 Remove old ${CONTAINER_NAME}, then start a new detached container.
  --restart              Remove old ${CONTAINER_NAME}, then start a new detached container.
  --stop                 Gracefully stop ${CONTAINER_NAME}; keep it for log inspection.
  --status               Show docker status for ${CONTAINER_NAME}.
  --logs                 Show the last 100 docker log lines for ${CONTAINER_NAME}.
  --follow-logs          Follow docker logs for ${CONTAINER_NAME}.
  --clean                Force-remove ${CONTAINER_NAME}.

Options:
  --vehicle USER@HOST     SSH target for the vehicle. Default: ${DEFAULT_VEHICLE}
  --password PASSWORD     Password for sshpass, if available. Default: ${DEFAULT_PASSWORD}
  --repo PATH             Vehicle repository path. Default: ${DEFAULT_REPO}
  --host HOST             UDP destination host for run_udp.sh.
  --port PORT             UDP destination port. Default: ${DEFAULT_PORT}
  --mode MODE             Forwarded to main_udp.py: sequential or simultaneous.
  --poll-interval SEC     Forwarded to main_udp.py for sequential mode.
  --sensor-period SEC     Forwarded to main_udp.py for simultaneous mode.
  --read-timeout SEC      Forwarded to main_udp.py. Use 0 for blocking reads.
  --print-local           Forwarded to main_udp.py.
                          Avoid this for long background runs; every packet goes to docker logs.
  --pull                  Run git pull --ff-only on the vehicle before start/restart.
  --                      Pass remaining arguments directly to main_udp.py.

Examples:
  $0 --host 192.168.2.1 --port 5005 --restart --mode sequential --poll-interval 0.1 --read-timeout 0.05
  $0 --logs
  $0 --clean
  $0 --stop
  $0 --status
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

VEHICLE="${DEFAULT_VEHICLE}"
PASSWORD="${DEFAULT_PASSWORD}"
REPO="${DEFAULT_REPO}"
HOST=""
PORT="${DEFAULT_PORT}"
ACTION=""
PULL=0
PRINT_LOCAL=0
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
        --password)
            require_value "$1" "${2:-}"
            PASSWORD="$2"
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
            PRINT_LOCAL=1
            shift
            ;;
        --pull)
            PULL=1
            shift
            ;;
        --start|--restart|--stop|--status|--logs|--follow-logs|--clean)
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

if [[ -z "${ACTION}" ]]; then
    ACTION="restart"
fi

if [[ "${ACTION}" == "start" || "${ACTION}" == "restart" ]]; then
    if [[ -z "${HOST}" ]]; then
        echo "--host is required for ${ACTION}." >&2
        exit 2
    fi
fi

if [[ "${PRINT_LOCAL}" == "1" && ( "${ACTION}" == "start" || "${ACTION}" == "restart" ) ]]; then
    echo "Warning: --print-local writes every UDP packet to docker logs for ${CONTAINER_NAME}." >&2
fi

REMOTE_MAIN_ARGS=("--host" "${HOST}" "--port" "${PORT}" "${RUN_ARGS[@]}")
PYTHON_CMD=$(quote_words "python3" "/workspaces/scripts/main_udp.py" "${REMOTE_MAIN_ARGS[@]}")
REPO_Q=$(printf "%q" "${REPO}")
CONTAINER_Q=$(printf "%q" "${CONTAINER_NAME}")
PYTHON_CMD_Q=$(printf "%q" "${PYTHON_CMD}")
ACTION_Q=$(printf "%q" "${ACTION}")
PULL_Q=$(printf "%q" "${PULL}")

SSH_OPTS=(-o StrictHostKeyChecking=no)
SSH_CMD=(ssh "${SSH_OPTS[@]}")
if [[ -n "${PASSWORD}" ]] && command -v sshpass >/dev/null 2>&1; then
    SSH_CMD=(sshpass -p "${PASSWORD}" ssh "${SSH_OPTS[@]}")
elif [[ -n "${PASSWORD}" ]]; then
    echo "Warning: sshpass is not installed; falling back to plain ssh." >&2
fi

"${SSH_CMD[@]}" "${VEHICLE}" \
    "REPO=${REPO_Q} CONTAINER=${CONTAINER_Q} PYTHON_CMD=${PYTHON_CMD_Q} ACTION=${ACTION_Q} PULL=${PULL_Q} bash -s" <<'REMOTE'
set -euo pipefail

container_exists() {
    docker container inspect "${CONTAINER}" >/dev/null 2>&1
}

status_sender() {
    docker ps -a --filter "name=^/${CONTAINER}$"
    if container_exists; then
        docker inspect -f 'state={{.State.Status}} exit_code={{.State.ExitCode}} started={{.State.StartedAt}} finished={{.State.FinishedAt}}' "${CONTAINER}"
    else
        echo "${CONTAINER} not running: container does not exist."
    fi
}

start_sender() {
    cd "${REPO}"

    if [[ "${PULL}" == "1" ]]; then
        git pull --ff-only
    fi

    docker rm -f "${CONTAINER}" 2>/dev/null || true
    docker run -d \
        --name "${CONTAINER}" \
        -v "${REPO}:/workspaces" \
        --net=host \
        --privileged \
        --volume=/dev:/dev \
        --volume=/lib/modules:/lib/modules \
        --volume=/sys:/sys \
        distance-sensor \
        sh -c "exec ${PYTHON_CMD}"
    echo "Started docker container ${CONTAINER}: ${PYTHON_CMD}"
}

stop_sender() {
    if container_exists; then
        docker stop "${CONTAINER}"
        echo "Stopped docker container ${CONTAINER}. Logs remain available until --clean."
    else
        echo "${CONTAINER} not running: container does not exist."
    fi
}

clean_sender() {
    docker rm -f "${CONTAINER}" 2>/dev/null && echo "Removed docker container ${CONTAINER}." || echo "${CONTAINER} not running: container does not exist."
}

show_logs() {
    if container_exists; then
        docker logs --tail 100 "${CONTAINER}"
    else
        echo "${CONTAINER} not running: container does not exist."
    fi
}

follow_logs() {
    if container_exists; then
        docker logs --tail 100 -f "${CONTAINER}"
    else
        echo "${CONTAINER} not running: container does not exist."
    fi
}

case "${ACTION}" in
    stop)
        stop_sender
        ;;
    status)
        status_sender
        ;;
    logs)
        show_logs
        ;;
    follow-logs)
        follow_logs
        ;;
    clean)
        clean_sender
        ;;
    start|restart)
        start_sender
        status_sender || true
        ;;
    *)
        echo "Unknown action: ${ACTION}" >&2
        exit 2
        ;;
esac
REMOTE
