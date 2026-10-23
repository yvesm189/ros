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

echo ">> the brand font is installed and is the system sans-serif"
# Captured rather than piped into grep: under `set -o pipefail`, `grep -q`
# closes the pipe early and fc-list dies with SIGPIPE, which would fail this
# check for a font that is perfectly well installed.
installed="$(fc-list : family 2>/dev/null || true)"
case "${installed}" in
    *"Funnel Display"*) ;;
    *) echo "Funnel Display is not installed" >&2; exit 1 ;;
esac
matched="$(fc-match sans-serif family 2>/dev/null)"
case "${matched}" in
    *"Funnel Display"*) echo "   sans-serif -> ${matched}" ;;
    *) echo "sans-serif resolves to '${matched}', expected Funnel Display" >&2; exit 1 ;;
esac
font="$(DCONF_PROFILE=user dconf read /org/gnome/desktop/interface/font-name)"
test "${font}" = "'Funnel Display 11'" || { echo "unexpected interface font: ${font}" >&2; exit 1; }
echo "   interface font = ${font}"

echo ">> the image pins no third-party browser or office suite"
favourites="$(DCONF_PROFILE=user dconf read /org/gnome/shell/favorite-apps)"
case "${favourites}" in
    *firefox*|*libreoffice*|*thunderbird*)
        echo "unexpected third-party application pinned: ${favourites}" >&2; exit 1 ;;
esac
echo "   favourites = ${favourites}"

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

echo ">> the store and the application defaults are in place"
test -x /usr/bin/ros-store
test -f /usr/share/applications/rw.ros.Store.desktop
test -f /usr/share/polkit-1/actions/rw.ros.store.policy
test -f /usr/lib/firefox-esr/ros.cfg
test -f /usr/lib/libreoffice/share/registry/ros.xcd
echo "   ros-store, its polkit action and the application defaults"

echo ">> the store is pinned to the dock"
favourites="$(DCONF_PROFILE=user dconf read /org/gnome/shell/favorite-apps)"
case "${favourites}" in
    *rw.ros.Store.desktop*) echo "   Isoko is pinned" ;;
    *) echo "the ROS Store is not pinned: ${favourites}" >&2; exit 1 ;;
esac

echo ">> the agent understands application policy"
python3 -c "
import sys
sys.path.insert(0, '/usr/lib/ros-agent')
import agent
assert hasattr(agent, 'apply_applications'), 'agent cannot apply applications'
assert agent.is_installed({'source': 'apt', 'reference': 'dpkg'}), 'dpkg should be installed'
assert not agent.is_installed({'source': 'apt', 'reference': 'no-such-package'})
print('   install detection works')
"

echo ">> agent reports its state"
ros-agent status >/dev/null
echo
echo "integration check passed"
