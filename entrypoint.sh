#!/bin/bash

DRIVER_NAME="ch9344"
DRIVER_DIR="/home/ch9344ser_linux/driver"
DRIVER_KO="${DRIVER_DIR}/${DRIVER_NAME}.ko"
CHECKSUM_FILE="${DRIVER_DIR}/.last_build_checksum"

is_module_loaded() {
    lsmod | grep -qE "${DRIVER_NAME}"
}

calculate_checksum() {
    find "${DRIVER_DIR}" -type f \( -name '*.c' -o -name '*.h' -o -name 'Makefile' \) -print0 | sort -z | xargs -0 sha1sum | sha1sum | cut -d' ' -f1
}

needs_building() {
    [ ! -f "${DRIVER_KO}" ] && return 0
    [ ! -f "${CHECKSUM_FILE}" ] && return 0
    [ "$(calculate_checksum)" != "$(cat "${CHECKSUM_FILE}")" ] && return 0
    return 1
}

cd "${DRIVER_DIR}" || { echo "Error: Unable to change to ${DRIVER_DIR}"; exit 1; }

if ! is_module_loaded; then
    if needs_building; then
        if ! make clean > /dev/null 2>&1 || ! make > /dev/null 2>&1; then
            echo "Error: Failed to build the driver module"
            exit 1
        fi
        calculate_checksum > "${CHECKSUM_FILE}"
    fi
    if ! sudo insmod "${DRIVER_KO}" > /dev/null 2>&1; then
        echo "Error: Failed to load the driver module"
        exit 1
    fi
fi

if is_module_loaded && ls /dev/ttyCH9344USB* > /dev/null 2>&1; then
    # echo "Driver ch9344 is loaded and devices are present."
    :
else
    echo "Error: Driver not loaded or devices not present. Check dmesg for details."
fi

cd - > /dev/null 2>&1 || true