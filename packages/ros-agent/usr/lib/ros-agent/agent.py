#!/usr/bin/env python3
"""ROS management agent.

Runs on every ROS workstation. It enrolls the machine with a ROS Console
server, reports inventory on a timer, and applies the desktop policy the
server hands back.

Deliberately written against the Python standard library only: the agent has
to keep working on a minimal image, during a partial upgrade, and before any
pip-installed dependency exists.

Usage:
    ros-agent enroll [--server URL] [--key KEY]
    ros-agent sync                 # heartbeat + fetch + apply policy
    ros-agent apply                # re-apply the cached policy
    ros-agent status               # what this machine thinks it is
"""

from __future__ import annotations

import argparse
import configparser
import json
import logging
import os
import platform
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

AGENT_VERSION = "0.1.0"

CONFIG_PATH = os.environ.get("ROS_AGENT_CONFIG", "/etc/ros/agent.conf")
STATE_DIR = os.environ.get("ROS_AGENT_STATE", "/var/lib/ros-agent")
IDENTITY_PATH = os.path.join(STATE_DIR, "identity.json")
POLICY_CACHE_PATH = os.path.join(STATE_DIR, "policy.json")
# The catalogue is public - it is a shop window - and the ROS Store runs as
# the person using the machine, so it lives outside the agent's private state
# directory where that person can actually read it.
CATALOGUE_CACHE_DIR = os.environ.get("ROS_CATALOGUE_DIR", "/var/cache/ros-agent")
CATALOGUE_CACHE_PATH = os.path.join(CATALOGUE_CACHE_DIR, "catalogue.json")

# Where the agent writes the policy it receives. 50- sorts after the defaults
# shipped by ros-branding (00-40), so the fleet can override the image without
# either side editing the other's files.
DCONF_DB_DIR = os.environ.get("ROS_DCONF_DIR", "/etc/dconf/db/ros.d")
MANAGED_KEYFILE = "50-managed"

log = logging.getLogger("ros-agent")


# --------------------------------------------------------------------------- #
# Configuration and identity
# --------------------------------------------------------------------------- #
class Config:
    def __init__(self, path: str = CONFIG_PATH) -> None:
        parser = configparser.ConfigParser()
        parser.read(path)
        self.path = path
        self.server = os.environ.get(
            "ROS_SERVER", parser.get("server", "url", fallback="")
        ).rstrip("/")
        self.enrollment_key = os.environ.get(
            "ROS_ENROLLMENT_KEY", parser.get("server", "enrollment_key", fallback="")
        )
        self.verify_tls = parser.getboolean("server", "verify_tls", fallback=True)
        self.timeout = parser.getint("agent", "timeout", fallback=20)
        self.log_level = parser.get("agent", "log_level", fallback="INFO").upper()
        self.apply_policy = parser.getboolean("agent", "apply_policy", fallback=True)

    @property
    def configured(self) -> bool:
        return bool(self.server)


def read_identity() -> Optional[Dict[str, Any]]:
    try:
        with open(IDENTITY_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def write_identity(identity: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = IDENTITY_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(identity, handle, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, IDENTITY_PATH)


# --------------------------------------------------------------------------- #
# Inventory
# --------------------------------------------------------------------------- #
def _run(cmd, default: str = "") -> str:
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, check=False
        )
        return out.stdout.strip() or default
    except (OSError, subprocess.SubprocessError):
        return default


def _read_file(path: str, default: str = "") -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return default


def machine_id() -> str:
    """Stable per-installation identifier.

    /etc/machine-id is regenerated on first boot of an image, which is exactly
    the behaviour we want: a machine re-imaged from the same ISO enrolls as a
    new device rather than silently taking over the old one's record.
    """
    value = _read_file("/etc/machine-id") or _read_file("/var/lib/dbus/machine-id")
    return value or socket.gethostname()


def os_release() -> Dict[str, str]:
    data: Dict[str, str] = {}
    for line in _read_file("/etc/os-release").splitlines():
        if "=" in line and not line.startswith("#"):
            key, _, value = line.partition("=")
            data[key.strip()] = value.strip().strip('"')
    return data


def _cpu_model() -> str:
    for line in _read_file("/proc/cpuinfo").splitlines():
        if line.lower().startswith(("model name", "hardware", "cpu model")):
            return line.split(":", 1)[-1].strip()
    return platform.processor() or "unknown"


def _memory_mb() -> int:
    for line in _read_file("/proc/meminfo").splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) // 1024
    return 0


def _disk_gb(path: str = "/") -> Dict[str, int]:
    try:
        stat = os.statvfs(path)
    except OSError:
        return {"total_gb": 0, "free_gb": 0}
    total = stat.f_blocks * stat.f_frsize
    free = stat.f_bavail * stat.f_frsize
    return {"total_gb": total // (1024 ** 3), "free_gb": free // (1024 ** 3)}


def _primary_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No packet is sent; this only asks the kernel which route would be used.
        sock.connect(("192.0.2.1", 9))
        return sock.getsockname()[0]
    except OSError:
        return ""
    finally:
        sock.close()


def collect_inventory() -> Dict[str, Any]:
    release = os_release()
    return {
        "hostname": socket.gethostname(),
        "machine_id": machine_id(),
        "os_name": release.get("NAME", "unknown"),
        "os_version": release.get("VERSION_ID", "unknown"),
        "os_pretty": release.get("PRETTY_NAME", "unknown"),
        "kernel": platform.release(),
        "arch": platform.machine(),
        "cpu_model": _cpu_model(),
        "cpu_count": os.cpu_count() or 0,
        "memory_mb": _memory_mb(),
        "disk": _disk_gb(),
        "ip_address": _primary_ip(),
        "uptime_seconds": int(float(_read_file("/proc/uptime", "0 0").split()[0])),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", "GNOME"),
        "gnome_shell": _run(["gnome-shell", "--version"], "n/a"),
        "agent_version": AGENT_VERSION,
        "collected_at": int(time.time()),
    }


# --------------------------------------------------------------------------- #
# Transport
# --------------------------------------------------------------------------- #
class ServerError(RuntimeError):
    pass


def request(
    config: Config,
    method: str,
    path: str,
    payload: Optional[Dict[str, Any]] = None,
    token: Optional[str] = None,
) -> Dict[str, Any]:
    url = config.server + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "ros-agent/%s" % AGENT_VERSION)
    if token:
        req.add_header("Authorization", "Bearer %s" % token)

    try:
        with urllib.request.urlopen(req, timeout=config.timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise ServerError("%s %s -> HTTP %s: %s" % (method, path, exc.code, detail))
    except urllib.error.URLError as exc:
        raise ServerError("%s %s -> %s" % (method, path, exc.reason))

    return json.loads(body) if body else {}


# --------------------------------------------------------------------------- #
# Policy application
# --------------------------------------------------------------------------- #
def render_dconf_keyfile(policy: Dict[str, Any]) -> str:
    """Turn the policy's dconf block into a dconf keyfile.

    Values are passed through as GVariant text exactly as the server sends
    them, so a string has to arrive already quoted ("'prefer-dark'"). The
    console is responsible for that; see docs/agent-protocol.md.
    """
    lines = [
        "# Managed by ros-agent. Local edits are overwritten on every sync.",
        "# Policy: %s (revision %s)"
        % (policy.get("name", "unnamed"), policy.get("revision", 0)),
        "",
    ]
    for section in sorted(policy.get("dconf", {})):
        lines.append("[%s]" % section.strip("/"))
        for key, value in sorted(policy["dconf"][section].items()):
            lines.append("%s=%s" % (key, value))
        lines.append("")
    return "\n".join(lines)


def apply_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    os.makedirs(os.path.join(DCONF_DB_DIR, "locks"), exist_ok=True)

    keyfile = os.path.join(DCONF_DB_DIR, MANAGED_KEYFILE)
    with open(keyfile, "w", encoding="utf-8") as handle:
        handle.write(render_dconf_keyfile(policy))

    lockfile = os.path.join(DCONF_DB_DIR, "locks", MANAGED_KEYFILE)
    locks = policy.get("locks") or []
    if locks:
        with open(lockfile, "w", encoding="utf-8") as handle:
            handle.write("# Managed by ros-agent.\n")
            handle.write("\n".join(locks) + "\n")
    elif os.path.exists(lockfile):
        os.unlink(lockfile)

    result = subprocess.run(
        ["dconf", "update"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError("dconf update failed: %s" % result.stderr.strip())

    log.info(
        "applied policy '%s' revision %s (%d sections, %d locks)",
        policy.get("name", "unnamed"),
        policy.get("revision", 0),
        len(policy.get("dconf", {})),
        len(locks),
    )

    detail = {"sections": len(policy.get("dconf", {})), "locks": len(locks)}

    # Settings first, applications second: a machine should look right even if
    # a package server is unreachable.
    applications = apply_applications(policy)
    if applications["installed"] or applications["failed"]:
        detail["applications"] = applications

    return detail


# --------------------------------------------------------------------------- #
# Applications
# --------------------------------------------------------------------------- #
def is_installed(app: Dict[str, Any]) -> bool:
    source = app.get("source", "apt")
    reference = app.get("reference", "")
    if not reference:
        return False

    if source == "flatpak":
        result = subprocess.run(
            ["flatpak", "info", reference],
            capture_output=True, text=True, check=False,
        )
        return result.returncode == 0

    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Status}", reference],
        capture_output=True, text=True, check=False,
    )
    return "install ok installed" in result.stdout


def install_application(app: Dict[str, Any]) -> None:
    source = app.get("source", "apt")
    reference = app["reference"]

    if source == "flatpak":
        command = ["flatpak", "install", "-y", "--noninteractive", reference]
    else:
        command = [
            "apt-get", "install", "-y", "--no-install-recommends", reference
        ]

    environment = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
    result = subprocess.run(
        command, capture_output=True, text=True, check=False,
        env=environment, timeout=1800,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "%s install of %s failed: %s"
            % (source, reference, (result.stderr or result.stdout).strip()[:300])
        )


def apply_applications(policy: Dict[str, Any]) -> Dict[str, Any]:
    """Install the applications a policy assigns, and only those.

    Nothing is ever removed here. A policy that stops listing an application
    means new machines will not get it; taking software off a machine somebody
    is using is a separate, destructive decision that a sync timer should not
    be making on its own.
    """
    applications = policy.get("applications") or []
    installed, failed, already = [], [], []

    missing = [app for app in applications if not is_installed(app)]
    if any(app.get("source", "apt") == "apt" for app in missing):
        # A freshly imaged machine has no package lists at all - the image build
        # throws them away to keep the ISO small - and a machine that has been
        # off for a month has stale ones. Refresh once per run, not per package.
        log.info("refreshing package lists")
        result = subprocess.run(
            ["apt-get", "update"],
            capture_output=True, text=True, check=False,
            env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"), timeout=600,
        )
        if result.returncode != 0:
            log.warning(
                "apt-get update failed, trying the installs anyway: %s",
                (result.stderr or result.stdout).strip()[:200],
            )

    for app in applications:
        name = app.get("name", app.get("reference", "?"))
        try:
            if is_installed(app):
                already.append(name)
                continue
            log.info("installing %s (%s:%s)", name, app.get("source"), app.get("reference"))
            install_application(app)
            installed.append(name)
        except Exception as exc:
            log.error("%s", exc)
            failed.append(name)

    if installed or failed:
        log.info(
            "applications: %d installed, %d already present, %d failed",
            len(installed), len(already), len(failed),
        )
    return {"installed": installed, "present": already, "failed": failed}


def fetch_catalogue(config: Config) -> Dict[str, Any]:
    """The store's shop window, cached so it still works offline."""
    identity = read_identity() or {}
    server = identity.get("server") or config.server
    if server:
        config.server = server.rstrip("/")
        try:
            catalogue = request(config, "GET", "/api/v1/catalogue")
            try:
                os.makedirs(CATALOGUE_CACHE_DIR, exist_ok=True)
                os.chmod(CATALOGUE_CACHE_DIR, 0o755)
                with open(CATALOGUE_CACHE_PATH, "w", encoding="utf-8") as handle:
                    json.dump(catalogue, handle, indent=2)
                os.chmod(CATALOGUE_CACHE_PATH, 0o644)
            except OSError:
                # A non-root caller can read the cache but not refresh it.
                pass
            return catalogue
        except ServerError as exc:
            log.warning("could not refresh the catalogue: %s", exc)

    try:
        with open(CATALOGUE_CACHE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"applications": []}


def cache_policy(policy: Dict[str, Any]) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(POLICY_CACHE_PATH, "w", encoding="utf-8") as handle:
        json.dump(policy, handle, indent=2)


def cached_policy() -> Optional[Dict[str, Any]]:
    try:
        with open(POLICY_CACHE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_enroll(config: Config, args: argparse.Namespace) -> int:
    server = (args.server or config.server).rstrip("/")
    key = args.key or config.enrollment_key
    if not server:
        log.error("no server URL: pass --server or set it in %s", config.path)
        return 2
    config.server = server

    existing = read_identity()
    if existing and not args.force:
        log.info("already enrolled as %s; use --force to re-enroll", existing["device_id"])
        return 0

    payload = {
        "enrollment_key": key,
        "hostname": socket.gethostname(),
        "machine_id": machine_id(),
        "inventory": collect_inventory(),
    }
    response = request(config, "POST", "/api/v1/enroll", payload)
    write_identity(
        {
            "device_id": response["device_id"],
            "token": response["token"],
            "server": server,
            "enrolled_at": int(time.time()),
        }
    )
    log.info("enrolled as device %s on %s", response["device_id"], server)
    return 0


def cmd_sync(config: Config, args: argparse.Namespace) -> int:
    identity = read_identity()
    if not identity:
        log.info("not enrolled yet; attempting enrollment first")
        if cmd_enroll(config, argparse.Namespace(server=None, key=None, force=False)):
            return 2
        identity = read_identity()
        if not identity:
            return 2

    config.server = identity.get("server", config.server).rstrip("/")
    device_id = identity["device_id"]
    token = identity["token"]
    local = cached_policy() or {}

    heartbeat = request(
        config,
        "POST",
        "/api/v1/devices/%s/heartbeat" % device_id,
        {
            "inventory": collect_inventory(),
            "agent_version": AGENT_VERSION,
            "policy_revision": local.get("revision", 0),
        },
        token=token,
    )

    remote_revision = heartbeat.get("policy_revision", 0)
    if remote_revision == local.get("revision", 0) and not args.force:
        log.info("policy revision %s already applied", remote_revision)
        return 0

    policy = request(
        config, "GET", "/api/v1/devices/%s/policy" % device_id, token=token
    )
    if not config.apply_policy:
        log.warning("apply_policy is disabled in %s; policy fetched but not applied",
                    config.path)
        cache_policy(policy)
        return 0

    try:
        detail = apply_policy(policy)
        status = "applied"
    except Exception as exc:  # reported to the server, then re-raised to the log
        detail = {"error": str(exc)}
        status = "failed"
        log.error("policy application failed: %s", exc)

    if status == "applied":
        cache_policy(policy)

    # Keep the store's shop window current while we have the server anyway.
    fetch_catalogue(config)

    request(
        config,
        "POST",
        "/api/v1/devices/%s/policy-result" % device_id,
        {"revision": policy.get("revision", 0), "status": status, "detail": detail},
        token=token,
    )
    return 0 if status == "applied" else 1


def cmd_apply(config: Config, args: argparse.Namespace) -> int:
    policy = cached_policy()
    if not policy:
        log.error("no cached policy at %s; run `ros-agent sync` first", POLICY_CACHE_PATH)
        return 2
    apply_policy(policy)
    return 0


def cmd_catalogue(config: Config, args: argparse.Namespace) -> int:
    catalogue = fetch_catalogue(config)
    for app in catalogue.get("applications", []):
        app["installed"] = is_installed(app)
    print(json.dumps(catalogue, indent=2))
    return 0


def cmd_app(config: Config, args: argparse.Namespace) -> int:
    """Install or remove one application by its catalogue slug.

    This is what the ROS Store calls through pkexec. It takes a slug rather
    than a package name so that the store cannot be talked into installing
    something that is not in the catalogue.
    """
    catalogue = fetch_catalogue(config)
    wanted = None
    for app in catalogue.get("applications", []):
        if app.get("slug") == args.slug:
            wanted = app
            break

    if wanted is None:
        log.error("no application '%s' in the catalogue", args.slug)
        return 2

    if args.action == "install":
        if is_installed(wanted):
            log.info("%s is already installed", wanted["name"])
            return 0
        try:
            install_application(wanted)
        except Exception as exc:
            log.error("%s", exc)
            return 1
        log.info("installed %s", wanted["name"])
        return 0

    # remove
    source = wanted.get("source", "apt")
    reference = wanted["reference"]
    if source == "flatpak":
        command = ["flatpak", "uninstall", "-y", "--noninteractive", reference]
    else:
        command = ["apt-get", "remove", "-y", reference]
    result = subprocess.run(
        command, capture_output=True, text=True, check=False,
        env=dict(os.environ, DEBIAN_FRONTEND="noninteractive"), timeout=1800,
    )
    if result.returncode != 0:
        log.error("removing %s failed: %s", wanted["name"],
                  (result.stderr or result.stdout).strip()[:300])
        return 1
    log.info("removed %s", wanted["name"])
    return 0


def cmd_status(config: Config, args: argparse.Namespace) -> int:
    identity = read_identity() or {}
    policy = cached_policy() or {}
    print(
        json.dumps(
            {
                "agent_version": AGENT_VERSION,
                "server_configured": config.configured,
                "server": identity.get("server") or config.server or None,
                "enrolled": bool(identity),
                "device_id": identity.get("device_id"),
                "policy_revision": policy.get("revision", 0),
                "policy_name": policy.get("name"),
                "inventory": collect_inventory(),
            },
            indent=2,
        )
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="ros-agent", description=__doc__.splitlines()[0])
    parser.add_argument("--config", default=CONFIG_PATH)
    parser.add_argument("--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    enroll = sub.add_parser("enroll", help="register this machine with a console")
    enroll.add_argument("--server")
    enroll.add_argument("--key")
    enroll.add_argument("--force", action="store_true")
    enroll.set_defaults(func=cmd_enroll)

    sync = sub.add_parser("sync", help="heartbeat, fetch and apply policy")
    sync.add_argument("--force", action="store_true", help="apply even if unchanged")
    sync.set_defaults(func=cmd_sync)

    apply_cmd = sub.add_parser("apply", help="re-apply the cached policy offline")
    apply_cmd.set_defaults(func=cmd_apply)

    status = sub.add_parser("status", help="print local agent state as JSON")
    status.set_defaults(func=cmd_status)

    catalogue = sub.add_parser(
        "catalogue", help="print the application catalogue, with install state"
    )
    catalogue.set_defaults(func=cmd_catalogue)

    app_cmd = sub.add_parser("app", help="install or remove a catalogue application")
    app_cmd.add_argument("action", choices=["install", "remove"])
    app_cmd.add_argument("slug")
    app_cmd.set_defaults(func=cmd_app)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0

    config = Config(args.config)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else getattr(logging, config.log_level, 20),
        format="%(levelname)s %(message)s",
    )

    if args.command in ("sync",) and not config.configured and not read_identity():
        # An unmanaged ROS install is a supported configuration: the timer fires,
        # finds no server, and exits quietly instead of filling the journal.
        log.info("no server configured in %s; nothing to do", config.path)
        return 0

    try:
        return args.func(config, args)
    except ServerError as exc:
        log.error("%s", exc)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
