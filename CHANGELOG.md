# Changelog

Notable changes to ROS. Versions follow [semantic versioning](https://semver.org);
before 1.0 the minor number carries breaking changes.

## 0.1.0 — 2026-10-23

First working version. The whole chain runs: build an image, enroll a machine,
change its desktop from a browser, watch the change land.

### Image

- Debian 13 (trixie) with GNOME, built with `live-build`, amd64 and arm64
- ROS identity: SVG wallpapers in light and dark, logo, Plymouth boot splash,
  GDM login screen, GTK and libadwaita accent colours
- Default desktop policy as a system dconf database, with a deliberately short
  list of locked keys
- Windows-friendly defaults: bottom dock via dash-to-dock, window buttons on
  the right, working tray icons
- English, French and Kinyarwanda locales
- Firefox and Chromium enterprise policy, telemetry off

### Packages

- `ros-branding`, `ros-agent` and the `ros-desktop-base` metapackage, built
  from plain file trees with `dpkg-deb` — no debhelper, no build dependencies
- Installable on an existing Debian 13 machine without building an ISO

### Management

- `ros-agent`: standard-library Python on a systemd timer; enrolls, reports
  hardware and OS inventory, applies policy as a dconf keyfile, reports the
  result, and caches the policy so it can re-apply offline
- ROS Console: FastAPI and SQLite, with device list and detail, policy groups,
  a desktop policy editor and an activity log
- The editor previews the exact keyfile the agent will write, from the same
  code path the agent uses
- Per-device bearer tokens, stored hashed and compared in constant time; a
  rotatable shared enrollment key

### Development

- `make` targets for packages, ISO, preview, console, a disposable managed
  workstation, tests and linting
- Builds work on macOS without installing Debian tooling: the scripts re-run
  themselves in containers
- CI: lint, unit tests, package install on a clean Debian 13, and a device API
  check against the real console image
- A browser-accessible desktop preview: the real GNOME session with the real
  branding and agent, served over noVNC, so the desktop and the management loop
  can be seen in about a minute instead of a multi-hour image build
