#!/bin/bash
# Integration check: install the ROS packages on a clean Debian 13 and prove
# the policy chain works end to end.
#
# Runs inside a container (see `make check` or the CI workflow), not on a host:
# it installs packages and rewrites /etc/dconf.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
export DEBIAN_FRONTEND=noninteractive

echo ">> installing dependencies"
apt-get -qq update >/dev/null
apt-get -qq install -y --no-install-recommends \
    dconf-cli dconf-gsettings-backend python3 systemd ca-certificates >/dev/null

echo ">> installing ROS packages"
apt-get -qq install -y --no-install-recommends ./out/packages/*.deb >/dev/null

echo ">> every database named in the dconf profile must compile"
for db in ros local gdm; do
    test -f "/etc/dconf/db/${db}" || { echo "missing compiled db: ${db}" >&2; exit 1; }
    echo "   /etc/dconf/db/${db}"
done

echo ">> ROS defaults are readable through the profile"
scheme="$(DCONF_PROFILE=user dconf read /org/gnome/desktop/interface/color-scheme)"
test "${scheme}" = "'prefer-dark'" || { echo "unexpected default: ${scheme}" >&2; exit 1; }
echo "   color-scheme = ${scheme}"

echo ">> a policy from a server overrides those defaults"
python3 -c "
import sys
sys.path.insert(0, '/usr/lib/ros-agent')
import agent
agent.apply_policy({
    'name': 'integration-check',
    'revision': 1,
    'dconf': {'org/gnome/desktop/interface': {'color-scheme': \"'prefer-light'\"}},
    'locks': ['/org/gnome/desktop/interface/color-scheme'],
})
"
scheme="$(DCONF_PROFILE=user dconf read /org/gnome/desktop/interface/color-scheme)"
test "${scheme}" = "'prefer-light'" || { echo "policy did not apply: ${scheme}" >&2; exit 1; }
echo "   color-scheme = ${scheme} (from policy)"

echo ">> the lock is in place"
grep -q "/org/gnome/desktop/interface/color-scheme" /etc/dconf/db/ros.d/locks/50-managed
echo "   locked"

echo ">> agent reports its state"
ros-agent status >/dev/null
echo
echo "integration check passed"
