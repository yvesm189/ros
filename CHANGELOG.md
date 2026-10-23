# Changelog

Notable changes to ROS. Versions follow [semantic versioning](https://semver.org);
before 1.0 the minor number carries breaking changes.

## Unreleased

### Added

- **Software installation is locked down** (`ros-lockdown`). Isoko is the only
  way software is installed on a ROS workstation: desktop accounts hold no
  administrative rights, PackageKit, apt and Flatpak's own authorisations are
  refused by polkit, and GNOME Software is no longer shipped. Installing from
  the catalogue needs no password, because the agent accepts a catalogue slug
  rather than a package name - the bound is on what can be installed, not on
  who may ask.
- **Approved commands.** A policy group lists `name = command line` entries
  that become `ros-run <name>` on the workstation. Commands are stored as
  argument lists and take no user input, so an approved command cannot be
  turned into a different one, and nothing outside the list runs as root.
- **Uploaded packages as a catalogue source.** An application can carry a
  `.deb` or `.flatpak` uploaded to the console instead of a reference into
  somebody else's repository. The console records the SHA-256, machines
  download it over an authenticated request, and a download that does not match
  what was published is never installed.

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

### Fixed

- **Logging in no longer drops the VNC connection.** Two separate causes, one
  symptom. Debian 13 ships no `gnome-xorg.desktop` - only Wayland sessions - so
  LightDM silently fell back to `lightdm-xsession`, which exits immediately and
  takes the seat, and the connection, with it; the preview now installs
  `gnome-session-xsession`. And GNOME 48 leaves its systemd user units running
  after a VNC client disconnects, so the *second* login found
  `gnome-session-manager@.service` already active and failed the same way -
  LightDM now tears the user's units down when a session ends.
- The agent waits for the dpkg lock instead of failing on it, so a sync that
  collides with unattended upgrades catches up rather than giving up.
- A command approved on a machine that does not have the binary reports that in
  those words rather than raising a traceback.

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
