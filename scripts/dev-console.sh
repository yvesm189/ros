#!/usr/bin/env bash
# Run the ROS console locally with auto-reload, in a virtualenv.
#
# This is the fast path for working on the UI. `make console` runs the same
# thing in Docker, which is what a deployment looks like.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONSOLE="${ROOT}/management/console"
VENV="${CONSOLE}/.venv"

if [ ! -d "${VENV}" ]; then
    echo ">> creating virtualenv in ${VENV}"
    python3 -m venv "${VENV}"
    "${VENV}/bin/pip" install --quiet --upgrade pip
    "${VENV}/bin/pip" install --quiet -r "${CONSOLE}/requirements.txt"
fi

# The Docker build stages these; the virtualenv path has to do it too, or the
# console falls back to a system font and stops looking like ROS.
mkdir -p "${CONSOLE}/app/static/fonts"
cp "${ROOT}/branding/fonts/FunnelDisplay[wght].ttf" "${CONSOLE}/app/static/fonts/funnel-display.ttf"
cp "${ROOT}/branding/fonts/SpaceGrotesk[wght].ttf" "${CONSOLE}/app/static/fonts/space-grotesk.ttf"

export ROS_DB_PATH="${ROS_DB_PATH:-${CONSOLE}/ros.db}"
export ROS_ADMIN_PASSWORD="${ROS_ADMIN_PASSWORD:-ros-admin}"

echo ">> console on http://127.0.0.1:${ROS_PORT:-8000}  (password: ${ROS_ADMIN_PASSWORD})"
cd "${CONSOLE}"
exec "${VENV}/bin/uvicorn" app.main:app --reload --host 127.0.0.1 --port "${ROS_PORT:-8000}"
