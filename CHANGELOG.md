# Changelog

Notable changes to ROS. Versions follow [semantic versioning](https://semver.org);
before 1.0 the minor number carries breaking changes.

## Unreleased

### Added

- **An application catalogue and a store.** The console publishes a catalogue
  of ROS applications built on open source upstreams - Urubuga (browser),
  Inyandiko, Imibare and Imurika (documents, spreadsheets, slides), Umusomyi
  (PDF) and the rest - and a policy group hands a machine the ones it should
  have. `ros-agent` installs what is missing on its next sync and never removes
  anything, because uninstalling software somebody is using is not a decision
  for a timer.
- **Isoko, the ROS Store** (`ros-store`): a GTK4 application that browses the
  catalogue and installs from it. It runs as the person at the keyboard and
  shells out through `pkexec` to the agent, which accepts a catalogue slug and
  never a package name - so the authorisation cannot become "install anything".
- **`ros-app-defaults`**: the configuration that makes catalogue applications
  behave like part of ROS - the brand font inside documents and web pages,
  telemetry off, no first-run prompts. Inert until the application it
  configures is installed.
- **A login screen in the desktop preview.** It now boots LightDM with a
  ROS-themed greeter and a real GNOME session behind it, instead of dropping
  straight into a shell nobody logged into.

### Changed

- **The system font is now Funnel Display**, matching the RHost console at
  rhost.rw. It ships in a new `ros-fonts` package together with Space Grotesk
  for display text, and a fontconfig rule makes it the generic `sans-serif` -
  so it is the system font, not just the GNOME interface font. Noto and DejaVu
  stay behind it for the coverage Funnel Display does not have.
- **Removed Firefox, LibreOffice and Thunderbird from the image**, along with
  their policy files and dock entries. The basic application set is being built
  as ROS applications on open source upstreams; see `docs/applications.md`.
  Until those land the image ships the GNOME system tools only.
- **The desktop preview serves plain VNC on :5900** instead of noVNC over HTTP.
  Xvnc replaces the Xvfb/x11vnc/websockify stack, so there is one process
  instead of three, and any VNC client can connect.
- Window controls keep GNOME's appearance - minimise, maximise, close on the
  right - with one geometric fix so each glyph sits centred in its circle.
- The brand typefaces live once, in `branding/fonts/`. The package build and
  the console build both stage them from there rather than keeping copies.

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
