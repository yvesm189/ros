#!/bin/bash
# Prepare the ROS desktop preview, then let LightDM take over.
#
# Runs as root under systemd, before lightdm.service: enrolls the machine with
# a console if one was given, gives the desktop user a password to log in with,
# and applies the requested screen geometry.
set -uo pipefail

log() { echo "[ros-preview] $*"; }

# systemd does not pass PID 1's environment to the services it starts, so the
# variables given to `docker run -e ...` are invisible here. Read them back off
# PID 1 rather than making the caller write a file into the container.
load_container_env() {
    [ -r /proc/1/environ ] || return 0
    while IFS='=' read -r -d '' name value; do
        case "${name}" in
            ROS_SERVER|ROS_ENROLLMENT_KEY|GEOMETRY|ROS_PASSWORD)
                [ -z "${!name:-}" ] && export "${name}=${value}"
                ;;
        esac
    done < /proc/1/environ
}
load_container_env

GEOMETRY="${GEOMETRY:-1600x900}"
PASSWORD="${ROS_PASSWORD:-ros}"

# ------------------------------------------------------------------ account --
# The password lives in the container's runtime state, never in an image layer.
echo "ros:${PASSWORD}" | chpasswd
log "login is ros / ${PASSWORD}"

# ----------------------------------------------------------------- geometry --
width="${GEOMETRY%x*}"
height="${GEOMETRY#*x}"
if [ -n "${width}" ] && [ -n "${height}" ]; then
    sed -i "s/^width=.*/width=${width}/;s/^height=.*/height=${height}/" /etc/lightdm/lightdm.conf
    log "screen ${width}x${height}"
fi

# --------------------------------------------------------------- management --
if [ -n "${ROS_SERVER:-}" ]; then
    log "enrolling with ${ROS_SERVER}"
    if ros-agent enroll --server "${ROS_SERVER}" --key "${ROS_ENROLLMENT_KEY:-}"; then
        ros-agent sync || true
    else
        log "enrollment failed; continuing with the image defaults"
    fi
    # From here the real systemd timer keeps the machine in sync; the preview
    # drop-in shortens its interval to 20 seconds.
    systemctl start ros-agent.timer || true
else
    log "no ROS_SERVER set; showing the image defaults only"
fi

log "handing over to LightDM; connect a VNC client to :5900"
