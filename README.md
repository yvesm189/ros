<div align="center">

<img src="docs/images/logo.png" width="96" alt="ROS logo">

# ROS

**A managed Debian desktop.**
A customised GNOME workstation image, and the server that configures every copy of it.

[![CI](https://github.com/yvesm189/ros/actions/workflows/ci.yml/badge.svg)](https://github.com/yvesm189/ros/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

<img src="docs/images/wallpaper-dark.png" width="760" alt="ROS default wallpaper">

</div>

---

## What this is

ROS is two things that only make sense together:

1. **A desktop image** — Debian 13 with GNOME, rebranded, with sane defaults and a
   small set of settings a user is not allowed to change.
2. **A console** — a web application that enrolls those workstations, keeps an
   inventory of them, and pushes desktop policy to them.

The interesting part is the second one. Plenty of projects rebrand a Linux
desktop; the reason to build one is so that a hundred copies of it can be
configured from one place without touching a hundred machines.

ROS is an early hobby project. It works end to end today — you can enroll a
machine, change its wallpaper, dock position and accent colour from a browser,
and watch the change land — but it is version 0.1.0 and nothing about it is
settled.

## How the pieces fit

```
   ┌──────────────────────────────┐          ┌─────────────────────────────┐
   │  ROS Console (FastAPI)       │          │  ROS workstation            │
   │                              │          │                             │
   │  policy groups               │  enroll  │  ros-agent  (systemd timer) │
   │  device inventory   ◀────────┼──────────┤    every 15 minutes         │
   │  activity log                │ heartbeat│                             │
   │                              │          │         writes              │
   │  compiles policy ──▶ dconf   │  policy  │           ▼                 │
   │  keyfile preview    ─────────┼─────────▶│  /etc/dconf/db/ros.d/       │
   └──────────────────────────────┘          │      50-managed             │
                                             │           │                 │
                                             │           ▼ dconf update    │
                                             │      GNOME session          │
                                             └─────────────────────────────┘
```

Policy is just a dconf database. That is the whole trick: GNOME already has a
system-wide settings layer with per-key locks, so ROS does not invent a
configuration system — it writes the one GNOME already reads, and the agent is
small enough to audit in an afternoon.

Precedence, lowest to highest:

```
GNOME defaults  ◀  ROS image defaults  ◀  site keyfiles  ◀  console policy  ◀  the user
                   /etc/dconf/db/ros.d    /etc/dconf/db     50-managed        (unless locked)
                   00-40                   local.d
```

## Quick start

Everything runs locally. You need Docker, Python 3, and make.

**1. Start the console**

```bash
make console          # Docker, http://127.0.0.1:8000
# or
make console-dev      # virtualenv with auto-reload
```

Sign in with the default password `ros-admin`, then open **Settings** and copy
the enrollment key.

**2. Start a workstation to manage**

This gives you a real managed machine in a container — the same packages, the
same agent, the same policy — without building an image:

```bash
make agent-dev KEY=<the enrollment key>
```

**3. Change something and watch it land**

In the console, open **Policies → Default**, set the accent colour to teal and
the dock to the left, and save. Then in the container shell:

```bash
ros-agent sync
cat /etc/dconf/db/ros.d/50-managed
```

**4. Build a bootable image**

```bash
make iso              # amd64, what an office PC boots
make iso-arm64        # native speed on Apple silicon
make preview          # boot the newest ISO in QEMU
```

On Apple silicon an amd64 ISO builds under emulation and takes hours. Build
arm64 while you are working on the desktop, and amd64 when you need the real
thing.

## Repository layout

| Path | What it is |
|---|---|
| `base/live-build/` | The image: package lists, chroot hooks, ISO configuration |
| `packages/ros-branding/` | Wallpapers, logo, boot splash, GTK accent, the default dconf policy |
| `packages/ros-agent/` | The management agent and its systemd timer |
| `packages/ros-desktop-base/` | Metapackage: "this machine is a ROS workstation" |
| `management/console/` | The console — FastAPI, SQLite, server-rendered UI |
| `scripts/` | Build, preview and development entry points |
| `tests/` | Unit tests, and the container integration check |
| `docs/` | The documents listed below |

## Documentation

| Document | What it covers |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Why it is built this way, and what each decision cost |
| [docs/building.md](docs/building.md) | Building packages and ISOs, and what to do when a build breaks |
| [docs/branding.md](docs/branding.md) | Customising GNOME: colours, wallpaper, dock, splash, login screen |
| [docs/management.md](docs/management.md) | Running the console, enrolling machines, writing policy |
| [docs/agent-protocol.md](docs/agent-protocol.md) | The agent/console HTTP contract |
| [docs/roadmap.md](docs/roadmap.md) | What is next, and what is deliberately not being built yet |

## Development

```bash
make test     # unit tests, no containers needed
make check    # install the packages on a clean Debian 13 and verify policy applies
make lint     # shell and Python syntax
```

## Security posture

Being honest about where 0.1.0 stands:

- Device tokens are random, stored hashed, and compared in constant time.
- The enrollment key is shared and single-purpose: it buys a device token once.
- The console's admin login is a single password from `ROS_ADMIN_PASSWORD`.
  There is no user management, and sessions are server-side rows in SQLite.
- **The console speaks plain HTTP.** Put TLS in front of it before it is
  reachable by anything but localhost; the agent sends its bearer token on
  every request.
- The agent runs as root because it writes `/etc/dconf` — and only for that.
  Its systemd unit restricts it accordingly.

## License

[GPL-3.0-or-later](LICENSE). ROS is built from Debian, which is free software,
and stays that way.
