#!/usr/bin/env bash
# Run a ROS desktop you can open with a VNC client.
#
# Builds and runs a container with the real GNOME session, the real branding
# and font packages and the real management agent, on a TigerVNC server. Point
# it at a console and policy changes land on the desktop while you watch.
#
#   ./scripts/preview-desktop.sh                       # image defaults only
#   ./scripts/preview-desktop.sh --key <key>           # managed by the local console
#   ./scripts/preview-desktop.sh --password secret     # set the desktop login password
#
# Connect with any VNC client and you get the ROS login screen:
#
#   vncviewer 127.0.0.1:5900          # TigerVNC
#   open vnc://127.0.0.1:5900         # macOS Screen Sharing
#
# systemd runs as PID 1 inside the container because GNOME Shell requires
# logind, which is why this needs --privileged. It is a development tool: the
# port is published on 127.0.0.1 only, and it should stay that way.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(cat "${ROOT}/VERSION")"
NAME="${ROS_PREVIEW_NAME:-ros-desktop}"
PORT="${ROS_PREVIEW_PORT:-5900}"
BIND="${ROS_PREVIEW_BIND:-127.0.0.1}"
GEOMETRY="${GEOMETRY:-1600x900}"
SERVER="${ROS_SERVER:-http://host.docker.internal:8000}"
KEY="${ROS_ENROLLMENT_KEY:-}"
PASSWORD="${ROS_PASSWORD:-ros}"

while [ $# -gt 0 ]; do
    case "$1" in
        --key) KEY="$2"; shift 2 ;;
        --server) SERVER="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --password) PASSWORD="$2"; shift 2 ;;
        --geometry) GEOMETRY="$2"; shift 2 ;;
        --unmanaged) KEY=""; SERVER=""; shift ;;
        -h|--help) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [ ! -f "${ROOT}/out/packages/ros-branding_${VERSION}_all.deb" ]; then
    echo ">> packages missing; building them"
    "${ROOT}/scripts/build-debs.sh" >/dev/null
fi

echo ">> building the preview image"
docker build -q -f "${ROOT}/preview/desktop/Dockerfile" \
    -t "ros-desktop-preview:${VERSION}" "${ROOT}" >/dev/null

docker rm -f "${NAME}" >/dev/null 2>&1 || true

echo ">> starting ${NAME}"
docker run -d --name "${NAME}" \
    --privileged \
    --cgroupns=host \
    -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    --tmpfs /run --tmpfs /run/lock \
    --add-host=host.docker.internal:host-gateway \
    --shm-size=512m \
    -p "${BIND}:${PORT}:5900" \
    -e GEOMETRY="${GEOMETRY}" \
    -e ROS_PASSWORD="${PASSWORD}" \
    ${SERVER:+-e ROS_SERVER="${SERVER}"} \
    ${KEY:+-e ROS_ENROLLMENT_KEY="${KEY}"} \
    "ros-desktop-preview:${VERSION}" >/dev/null

echo -n ">> waiting for the desktop"
for _ in $(seq 1 90); do
    # LightDM listens on 5900 once it is ready to hand out greeters; bash's
    # /dev/tcp avoids needing nc in the host environment.
    if (exec 3<>"/dev/tcp/${BIND}/${PORT}") 2>/dev/null; then
        exec 3>&- 2>/dev/null || true
        echo
        echo
        echo "   ROS login:    vnc://${BIND}:${PORT}"
        echo "   TigerVNC:     vncviewer ${BIND}:${PORT}"
        echo "   sign in as:   ros / ${PASSWORD}"
        [ -n "${KEY}" ] && echo "   managed by:   ${SERVER}"
        echo
        echo "   logs:  docker exec ${NAME} journalctl -u ros-preview.service -u lightdm"
        echo "   stop:  docker rm -f ${NAME}"
        exit 0
    fi
    echo -n "."
    sleep 2
done

echo
echo "the desktop did not come up; here is what it said:" >&2
docker exec "${NAME}" journalctl -u ros-preview.service --no-pager 2>&1 | tail -30 >&2
exit 1
