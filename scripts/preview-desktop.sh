#!/usr/bin/env bash
# Open a ROS desktop in a browser.
#
# Builds and runs a container with the real GNOME session, the real branding
# package and the real management agent, served over noVNC on :6080. Point it
# at a console and policy changes land on the desktop while you watch.
#
#   ./scripts/preview-desktop.sh                      # image defaults only
#   ./scripts/preview-desktop.sh --key <key>          # managed by the local console
#
# systemd runs as PID 1 inside the container because GNOME Shell requires
# logind, which is why this needs --privileged. It is a development tool; do
# not run it on anything exposed.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(cat "${ROOT}/VERSION")"
NAME="${ROS_PREVIEW_NAME:-ros-desktop}"
PORT="${ROS_PREVIEW_PORT:-6080}"
GEOMETRY="${GEOMETRY:-1600x900}"
SERVER="${ROS_SERVER:-http://host.docker.internal:8000}"
KEY="${ROS_ENROLLMENT_KEY:-}"

while [ $# -gt 0 ]; do
    case "$1" in
        --key) KEY="$2"; shift 2 ;;
        --server) SERVER="$2"; shift 2 ;;
        --port) PORT="$2"; shift 2 ;;
        --geometry) GEOMETRY="$2"; shift 2 ;;
        --unmanaged) KEY=""; SERVER=""; shift ;;
        -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
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
    -p "${PORT}:6080" \
    -e GEOMETRY="${GEOMETRY}" \
    ${SERVER:+-e ROS_SERVER="${SERVER}"} \
    ${KEY:+-e ROS_ENROLLMENT_KEY="${KEY}"} \
    "ros-desktop-preview:${VERSION}" >/dev/null

echo -n ">> waiting for the desktop"
for _ in $(seq 1 90); do
    if curl -fsS -o /dev/null "http://127.0.0.1:${PORT}/vnc.html" 2>/dev/null; then
        echo
        echo
        echo "   ROS desktop:  http://localhost:${PORT}/vnc.html?autoconnect=true&resize=scale"
        [ -n "${KEY}" ] && echo "   managed by:   ${SERVER}"
        echo
        echo "   logs:  docker logs -f ${NAME}"
        echo "   stop:  docker rm -f ${NAME}"
        exit 0
    fi
    echo -n "."
    sleep 2
done

echo
echo "the desktop did not come up; here is what it said:" >&2
docker logs "${NAME}" 2>&1 | tail -30 >&2
exit 1
