# Software and command policy

On a ROS workstation, **Isoko is the way software is installed**. Nothing else
is. Users have no administrative rights at all, and the exceptions are written
down in the management console rather than handed out as sudo.

The model is a phone's: install freely, but only from a catalogue the
organisation curates. The trust sits in the curation, not in the user.

## What a user can and cannot do

| | |
|---|---|
| Install from Isoko | **Yes** — no password, as many times as they like |
| `sudo` anything | **No** — desktop accounts are in no administrative group |
| `apt install` / `dpkg -i` | **No** — these need root, and the user is not root |
| Install through PackageKit or GNOME Software | **No** — refused by polkit, and GNOME Software is not shipped |
| `flatpak install` system-wide | **No** — refused by polkit |
| Run an approved command | **Yes** — `ros-run <name>`, for the names the console approved |
| Run anything else as root | **No** |

## How it is enforced

`ros-lockdown` installs `/etc/polkit-1/rules.d/50-ros-lockdown.rules`:

- `org.freedesktop.packagekit.*`, `org.debian.apt.*` and
  `org.freedesktop.Flatpak.*` return `NO` for anyone outside `ros-admins` and
  `sudo`. An administrator still gets the normal password prompt — this removes
  the path for users, not the capability from the machine.
- `rw.ros.store.manage-applications` and `rw.ros.commands.run` return `YES` for
  members of `ros-users`, which is every human account on the machine.

That second rule is the interesting one, and it is worth being explicit about
why it is a group test rather than `subject.local && subject.active`:

> GNOME 48 runs the shell, and everything launched from it, as systemd **user
> units** with no `XDG_SESSION_ID`. polkit cannot tie those processes back to
> the seat session, so a session-based rule prompts for a password on every
> single install — exactly what this design exists to avoid. The session test
> is kept as a second condition for processes that do carry a session.

The capability is bounded on the other side instead, which is where it belongs:

```
ros-agent app install <slug>     # a catalogue slug, never a package name
ros-agent run <name>             # an approved name, never a command line
```

The store passes a slug. `ros-run` passes a name. Neither ever passes something
the user typed, so "install from the store" cannot become "install anything",
and "run an approved command" cannot become "run anything".

`ros-agent` keeps `ros-users` in step with the accounts on the machine on every
sync, so a new user does not arrive to a store that asks for a password nobody
can answer.

## Approving commands

**Policies → a group → Elevated commands.** One per line:

```
restart-printing = systemctl restart cups   # Restart the print service
flush-dns        = resolvectl flush-caches  # Clear the DNS cache
collect-logs     = journalctl --since -1h --no-pager
```

The group page prints exactly what users on those machines will be able to run
as root. On the workstation:

```bash
ros-run                  # what this machine is allowed to run
ros-run restart-printing
```

Each command is stored as an **argument list**, not a shell string, and the
user supplies no part of it. An approved command therefore cannot be turned
into a different one by anything the user types.

If the console approves something a machine does not have, the agent says so in
those words rather than producing a traceback — that is a policy mistake, and
it should read like one.

## What this does not stop

Being honest about the edges:

- **`flatpak install --user`** does not go through polkit at all, so it cannot
  be refused this way. ROS ships **no Flatpak remote** by default, which is
  what actually removes the path; adding one is a management decision.
- **A binary a user downloads into their home directory** will run. Preventing
  that needs `/home` mounted `noexec`, which is a real option and a real
  trade-off — it also breaks legitimate tooling. ROS does not do it by default.
- **An administrator is still an administrator.** This constrains users, not
  people in `ros-admins` or `sudo`.
- `ros-lockdown` is a package. A machine where it is not installed falls back
  to each action's own defaults, which ask for an administrator password — safe,
  but it means the store stops being frictionless. Install it, or install
  `ros-desktop-base`, which depends on it.

## Checking a machine

```bash
id                       # a desktop user should be in ros-users and nothing else
ros-run                  # the approved list
ros-agent status         # includes approved_commands
pkcheck --action-id rw.ros.store.manage-applications --process $$
```
