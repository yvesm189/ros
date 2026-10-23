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
    return {"sections": len(policy.get("dconf", {})), "locks": len(locks)}


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
