#!/usr/bin/env bash
# Run a throwaway ROS workstation in a container and point it at a console.
#
# This is how you test the management loop without building an ISO: the
# container installs the real .deb packages, enrolls with the real agent, and
# applies the real policy. Everything except the GNOME session is identical to
# a workstation.
#
#   ./scripts/dev-agent.sh <enrollment-key> [server-url]
#
# The key is on the console's Settings page. Default server is the console
# running on this machine via `make console-dev`.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEY="${1:-${ROS_ENROLLMENT_KEY:-}}"
SERVER="${2:-${ROS_SERVER:-http://host.docker.internal:8000}}"
VERSION="$(cat "${ROOT}/VERSION")"

if [ -z "${KEY}" ]; then
    echo "usage: $0 <enrollment-key> [server-url]" >&2
    echo "       the key is shown on the console's Settings page" >&2
    exit 1
fi

if [ ! -f "${ROOT}/out/packages/ros-agent_${VERSION}_all.deb" ]; then
    echo ">> packages missing; building them"
    "${ROOT}/scripts/build-debs.sh" >/dev/null
fi

echo ">> starting a disposable ROS workstation against ${SERVER}"
exec docker run --rm -it \
    --add-host=host.docker.internal:host-gateway \
    -v "${ROOT}:/ros:ro" \
    -w /root \
    debian:trixie-slim \
    bash -c "
        set -e
        export DEBIAN_FRONTEND=noninteractive
        echo '>> installing the desktop policy and agent packages'
        apt-get -qq update >/dev/null
        apt-get -qq install -y --no-install-recommends \
            dconf-cli dconf-gsettings-backend python3 ca-certificates >/dev/null
        apt-get -qq install -y --no-install-recommends \
            /ros/out/packages/ros-branding_${VERSION}_all.deb \
            /ros/out/packages/ros-agent_${VERSION}_all.deb >/dev/null
        echo '>> enrolling'
        ros-agent enroll --server '${SERVER}' --key '${KEY}'
        ros-agent sync
        echo
        echo 'This shell is a managed ROS machine. Useful commands:'
        echo '  ros-agent sync --force        re-fetch and re-apply policy'
        echo '  ros-agent status              what this machine thinks it is'
        echo '  cat /etc/dconf/db/ros.d/50-managed'
        echo '  DCONF_PROFILE=user dconf dump /org/gnome/'
        echo
        exec bash
    "
