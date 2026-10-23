# Building

Three things can be built: the packages, the ISO, and the console image. The
packages are seconds, the console is a minute, the ISO is the long one.

## Requirements

| Host | What you need |
|---|---|
| macOS | Docker, Python 3, make. QEMU (`brew install qemu`) or UTM to preview. |
| Debian/Ubuntu | Same, or install `live-build dpkg-dev` and build natively. |

No host needs `dpkg` or `live-build` installed — both build scripts detect that
they are missing and re-run themselves inside a Debian container.

## Packages

```bash
make packages          # → out/packages/*.deb
```

Three packages come out:

| Package | Contents |
|---|---|
| `ros-branding` | Wallpapers, logo, splash, dconf defaults and locks, browser policy |
| `ros-agent` | The management agent, its systemd timer, `/etc/ros/agent.conf` |
| `ros-desktop-base` | Metapackage: GNOME + the two above |

They are built with `dpkg-deb` from plain file trees under `packages/` — no
debhelper, no build dependencies beyond dpkg itself. `scripts/build-debs.sh`
substitutes the version from `VERSION`, generates `conffiles` from everything
under `etc/`, normalises permissions and writes `md5sums`.

Installing `ros-desktop-base` on an existing Debian 13 machine is the supported
way to try ROS without an ISO.

## ISO

```bash
make iso               # amd64 - what an office PC boots
make iso-arm64         # arm64 - native speed on Apple silicon
```

What `scripts/build-iso.sh` does:

1. Builds the packages and copies them into
   `base/live-build/config/packages.chroot/`, where live-build installs
   everything it finds automatically.
2. Writes `config/includes.chroot/etc/ros/release` with the version, codename
   and build date. Chroot hooks cannot see the build environment, so this stamp
   is how the branding hook learns what it is building.
3. Runs `lb config && lb build` in a privileged `debian:trixie` container —
   live-build needs loop devices.
4. Copies the ISO to `out/` with a SHA-256 checksum.

**On Apple silicon**, an amd64 build runs under emulation and takes hours.
Build arm64 while you are iterating on the desktop and amd64 when you need the
image a real PC will boot. The ISO job in CI builds amd64 natively, which is
usually the better way to get one.

Expect roughly 2.5–3.5 GB of ISO and about 10 GB of scratch space.

### What the build does to the image

`base/live-build/config/hooks/normal/` runs in the chroot, in order:

| Hook | What it does |
|---|---|
| `0100-locales` | Generates `en_US`, `en_RW`, `fr_RW`, `fr_FR`, `rw_RW` |
| `0200-os-branding` | Rewrites `/usr/lib/os-release`, `/etc/issue`, `/etc/lsb-release` |
| `0300-dconf-compile` | `dconf update` and `glib-compile-schemas` |
| `0400-plymouth-theme` | Sets the ROS splash and rebuilds the initramfs |
| `0500-services` | Enables GDM, chrony and `ros-agent.timer` |
| `0600-flatpak-remote` | Adds Flathub |
| `9900-cleanup` | Purges caches, truncates logs, clears the machine ID |

Clearing `/etc/machine-id` matters: it is regenerated on first boot, which is
what makes each installed machine enroll as its own device.

## Preview

```bash
make preview                              # newest ISO in out/
./scripts/preview.sh out/ros-0.1.0-arm64.iso
```

The script picks `qemu-system-x86_64` or `qemu-system-aarch64` from the ISO
name, finds UEFI firmware for arm64, and enables `hvf` acceleration when the
guest architecture matches the host. An arm64 image on Apple silicon is
genuinely usable; an amd64 image is fully emulated and slow, but it does boot.

The ISO is an ordinary Debian live image, so UTM, VirtualBox and VMware open it
too. The live session user is `ros` with no password.

## Console image

```bash
docker build -t ros-console management/console
make console                 # build and run via compose
```

The image runs as an unprivileged user, keeps its database on a volume at
`/data`, and has a health check on `/api/v1/health`.

## Tests

```bash
make test      # unit tests: policy compilation, keyfile rendering, inventory
make check     # installs the packages on a clean Debian 13 and applies a policy
make lint      # shell and Python syntax
```

`make check` is the one that matters before a release: it proves the dconf
databases compile, the ROS defaults are readable through the profile, and a
policy from a server overrides them.

## Troubleshooting

**`lb build` fails unpacking the filesystem** — the container is not
privileged, or Docker's VM is out of disk. `docker system prune` and check
Docker Desktop's disk allocation.

**A package in a list cannot be found** — the name changed between Debian
releases. Check with
`docker run --rm debian:trixie-slim bash -c "apt-get update -qq && apt-cache policy <name>"`.
This is why the desktop list depends on `gnome-core` rather than naming each
GNOME application.

**The ISO boots to a black screen in QEMU** — missing or wrong UEFI firmware
for the guest architecture. Install `qemu` properly (`brew install qemu` ships
`edk2-aarch64-code.fd`) or boot the ISO in UTM.

**dconf warns about a missing database** — a database named in
`/etc/dconf/profile/user` has never been compiled. `ros-branding` ships a
placeholder in `local.d` precisely so `local` always exists; if you add a
database to the profile, give it a `.d` directory with at least one file.

**The agent enrolls but nothing changes on screen** — dconf applies to a GNOME
session at read time, so log out and back in. Check
`/etc/dconf/db/ros.d/50-managed` exists and `DCONF_PROFILE=user dconf read <key>`
returns what you expect.
