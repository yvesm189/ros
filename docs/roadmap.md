# Roadmap

What exists, what is next, and what is deliberately not being built yet.

## 0.1.0 — now

- Debian 13 + GNOME image built reproducibly from this repository
- ROS identity: wallpapers, logo, boot splash, accent colours, login screen
- Default desktop policy as a system dconf database, with locks
- `ros-agent`: enroll, heartbeat, inventory, apply policy, report result
- ROS Console: devices, policy groups, activity log, policy editor with an
  exact preview of the file the agent will write
- Local build and preview on macOS and Linux; CI that proves the chain works

## 0.2 — making it usable day to day

- **Apply now.** A policy change waits up to 15 minutes. The device page needs
  a button, which means the agent needs somewhere to listen or something to
  poll more cheaply.
- **Per-device overrides.** Today policy belongs to a group; one machine that
  needs one different setting has to get its own group.
- **Policy history and rollback.** Revisions increment but old ones are not
  kept. They should be, with a diff and a one-click revert.
- **Software inventory.** Which packages, which versions, across the fleet.
- **A real ISO in CI on every tag**, with the checksum published.

## 0.3 — beyond the desktop

Desktop settings are the part dconf handles well. Everything below is state
that belongs to the machine rather than the session, and the right tool for it
is Ansible rather than a bigger agent:

- Package and Flatpak sets per group
- Disk encryption with LUKS, and key escrow the organisation controls
- Directory enrollment — joining an existing Active Directory with SSSD, or
  FreeIPA where there is no directory yet
- An internal apt mirror with staged rings, so updates roll out to a test group
  before the fleet
- Compliance scanning with OpenSCAP against a written baseline

The agent would gain one job: run an Ansible pull. It would not grow a
configuration language of its own.

## Not yet, on purpose

- **Multi-tenancy and user accounts in the console.** One password is honest at
  this size. Adding roles before there are two administrators is overhead.
- **Remote desktop support.** MeshCentral already does this well; ROS should
  integrate with it, not reimplement it.
- **A custom GNOME Shell theme.** Shell themes are compiled gresource bundles
  tied to a shell version and break on every GNOME release. ROS stays on
  supported configuration surfaces.
- **Anything bigger than SQLite.** When one console process is not enough, the
  database goes first — but that is a real scaling problem, not a hypothetical
  one, and it will look different when it arrives.

## Open questions

- **Image-based updates.** `bootc`-style atomic images with rollback are the
  right long-term answer for a fleet, and the wrong answer for a project whose
  users know apt. Worth prototyping, not worth committing to.
- **Per-user policy.** dconf system databases are per-machine. Shared
  workstations with different policy per user need a different mechanism
  entirely.
- **How much to lock.** Every lock is a support call. The current set is five
  keys and that feels close to right.
