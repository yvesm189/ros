#!/bin/bash
# Start a ROS desktop on a TigerVNC server.
#
# Runs as root under systemd so that ros-agent can write /etc/dconf; the GNOME
# session itself runs as the unprivileged `ros` user.
set -uo pipefail

log() { echo "[ros-preview] $*"; }

# systemd does not pass PID 1's environment to the services it starts, so the
# variables given to `docker run -e ...` are invisible here. Read them back off
# PID 1 rather than making the caller write a file into the container.
load_container_env() {
    [ -r /proc/1/environ ] || return 0
    while IFS='=' read -r -d '' name value; do
        case "${name}" in
            ROS_SERVER|ROS_ENROLLMENT_KEY|GEOMETRY|VNC_PASSWORD)
                [ -z "${!name:-}" ] && export "${name}=${value}"
                ;;
        esac
    done < /proc/1/environ
}
load_container_env

GEOMETRY="${GEOMETRY:-1600x900}"

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

# ------------------------------------------------------------------ display --
# Xvnc is the X server and the VNC server in one process, so there is no Xvfb
# to pair with a separate x11vnc and nothing to keep in sync between them.
VNC_ARGS=(
    -geometry "${GEOMETRY}"
    -depth 24
    -rfbport 5900
    -AlwaysShared
    -desktop "ROS"
)

if [ -n "${VNC_PASSWORD:-}" ]; then
    install -d -m 700 /root/.vnc
    printf '%s\n' "${VNC_PASSWORD}" | vncpasswd -f > /root/.vnc/passwd
    chmod 600 /root/.vnc/passwd
    VNC_ARGS+=(-SecurityTypes VncAuth -PasswordFile /root/.vnc/passwd)
    log "starting Xvnc at ${GEOMETRY} on :5900 (password authentication)"
else
    # No password by default. The launcher publishes the port on 127.0.0.1
    # only; see scripts/preview-desktop.sh before changing that.
    VNC_ARGS+=(-SecurityTypes None)
    log "starting Xvnc at ${GEOMETRY} on :5900 (no authentication)"
fi

Xvnc :0 "${VNC_ARGS[@]}" >/dev/null 2>&1 &

# Wait for the X socket rather than for a client tool: xdpyinfo lives in
# x11-utils, which this image has no other reason to carry.
for _ in $(seq 1 60); do
    [ -S /tmp/.X11-unix/X0 ] && break
    sleep 0.25
done
[ -S /tmp/.X11-unix/X0 ] || { log "Xvnc did not start"; exit 1; }

# ------------------------------------------------------------------ session --
# Without gnome-session, the shell comes up sitting in the Activities overview
# and stays there. One Escape once it is drawing puts it on the desktop, which
# is what somebody opening this URL expects to see.
(
    for _ in $(seq 1 60); do
        pgrep -x gnome-shell >/dev/null && break
        sleep 1
    done
    sleep 6
    for _ in 1 2 3; do
        DISPLAY=:0 xdotool key Escape 2>/dev/null
        sleep 2
    done
    log "desktop ready"
) &


# systemd-run gives the session its own logind session and user bus, which is
# what GNOME Shell expects to find; runuser alone does not.
log "starting the GNOME session"
exec systemd-run --wait --pipe --uid=1000 --gid=1000 \
    --setenv=DISPLAY=:0 \
    --setenv=XDG_CURRENT_DESKTOP=GNOME \
    --setenv=XDG_SESSION_TYPE=x11 \
    --setenv=LIBGL_ALWAYS_SOFTWARE=1 \
    --setenv=GALLIUM_DRIVER=llvmpipe \
    --setenv=NO_AT_BRIDGE=1 \
    --setenv=LANG=en_US.UTF-8 \
    --unit=ros-gnome-session \
    dbus-run-session -- gnome-shell --x11
