# Architecture

How ROS is put together, and why. Where a decision cost something, that is
written down too — a design note that only lists advantages is marketing.

## The shape of it

ROS has three moving parts and one idea.

The idea: **GNOME already has a configuration system with policy semantics.**
dconf has a system-wide database layer, a profile that defines precedence, and
per-key locks that a user cannot override. ROS does not invent a configuration
language, an agent protocol for settings, or a templating system. It writes a
dconf keyfile and runs `dconf update`.

Everything else follows from that.

### 1. The image — `base/live-build/`

Debian 13 (trixie) plus GNOME, built with `live-build`. The configuration is a
directory of package lists and shell hooks, which is as close to "the build is
the repository" as Debian gets.

Choices worth naming:

- **Debian, not Ubuntu.** No vendor account, no CLA, no subscription for the
  long support tail. The cost is that hardware enablement lags — on very new
  laptops, Ubuntu would have worked out of the box where Debian needs backports.
- **Stock Debian kernel.** Secure Boot keeps working and firmware keeps
  matching. A custom kernel buys nothing ROS needs and breaks both.
- **`gnome-core`, not a hand-picked app list.** Debian moves applications in and
  out of the GNOME set between releases; depending on the metapackage means ROS
  gets whichever terminal and image viewer actually matches the shell version in
  the suite. The cost is slightly less control over image size.
- **ROS's own content ships as `.deb` packages**, not as files copied into the
  image. The image build drops them in `config/packages.chroot` and live-build
  installs them. The same packages install on an existing Debian machine, which
  means development does not require building an ISO.

### 2. The desktop identity — `packages/ros-branding/`

Wallpapers, logo, boot splash, GTK accent colours, browser policy, and the
default dconf database.

The branding is deliberately **not** a forked GNOME Shell theme. Shell themes
are compiled gresource bundles tied to a shell version, and they break on every
GNOME release. ROS instead uses what GNOME exposes as supported configuration:
the accent colour setting, wallpaper URIs, a libadwaita colour override in
`gtk.css`, and two packaged extensions. The result is less dramatic than a full
reskin, and it survives upgrades.

### 3. The management plane — `management/console/` and `packages/ros-agent/`

A FastAPI console with a SQLite database, and a standard-library-only Python
agent on a systemd timer.

- **SQLite, not PostgreSQL.** A console for a few hundred workstations is
  read-mostly and fits in one file, and one file is something a small team can
  back up. The cost is that this does not scale horizontally; if ROS ever needs
  more than one console process, the database goes first.
- **The agent uses only the standard library.** It has to keep working on a
  minimal image, during a partial upgrade, and before pip exists. The cost is
  hand-rolled HTTP with `urllib` instead of `requests`.
- **Pull, not push.** The agent asks the console for its policy on a timer.
  Laptops that roam, sleep and sit behind NAT are the normal case, and a push
  model would need every one of them reachable. The cost is latency: a policy
  change takes up to 15 minutes, and there is no "apply now" button yet.
- **Policy is compiled in two places.** The console compiles it to show an exact
  preview; the agent compiles it to write the file. That is duplication, and it
  is pinned by a test that renders both and asserts they are byte-identical.

## Why dconf rather than Ansible

Ansible is the obvious tool and ROS will probably grow into it. It is not the
right tool for *desktop settings* specifically:

- Desktop policy changes often and is edited by people who are not Linux
  administrators. A web form beats a YAML pull request for that audience.
- dconf locks are enforced by GNOME at read time. An Ansible-managed gsettings
  value is enforced only when Ansible next runs, so a user can change it back
  and keep it changed until the next play.
- The agent that applies dconf is 400 lines and needs no dependencies. Ansible
  needs Python on the target anyway, plus inventory, plus a way to reach the
  machine.

Ansible is the right answer for packages, disk encryption, directory
enrollment and the rest of the fleet's state. See [roadmap.md](roadmap.md).

## Precedence, exactly

`/etc/dconf/profile/user` reads:

```
user-db:user
system-db:local
system-db:ros
```

dconf reads databases in order and **the first one that has a value wins**, with
one exception: a key locked in any system database cannot be overridden by the
user database.

So, from weakest to strongest:

| Layer | Where | Who owns it |
|---|---|---|
| GNOME defaults | GSettings schemas | Debian |
| ROS defaults | `/etc/dconf/db/ros.d/00-40` | this repository |
| Console policy | `/etc/dconf/db/ros.d/50-managed` | the console, written by ros-agent |
| Site settings | `/etc/dconf/db/local.d/` | the local administrator |
| The user | `~/.config/dconf/user` | whoever is logged in, unless the key is locked |

The site layer sits *above* the console deliberately: an administrator standing
at a machine should be able to win an argument with a server.

## What a managed machine does

1. First boot: `ros-agent.timer` fires two minutes in.
2. If `/etc/ros/agent.conf` has no server, the agent logs one line and exits.
   An unmanaged ROS install is a supported configuration.
3. If it has a server and no identity, it enrolls: machine ID and inventory in,
   device ID and bearer token out, stored `0600` in `/var/lib/ros-agent`.
4. Every 15 minutes (plus up to 2 minutes of jitter, so a power cut does not
   turn into a thundering herd) it heartbeats with fresh inventory and the
   revision it currently has.
5. If the console reports a newer revision, the agent fetches the policy,
   writes `50-managed` and its lock file, runs `dconf update`, and reports the
   outcome. On failure it reports that too, and the device shows as failed in
   the console rather than silently drifting.
6. The applied policy is cached, so `ros-agent apply` re-applies it with no
   network at all.

## Known limitations

- No TLS in the box. The console speaks HTTP and expects a reverse proxy.
- One shared enrollment key, rotatable but not per-device or time-limited.
- No "apply now": a change waits for the next timer tick.
- Policy applies to a machine, not to a user — dconf system databases are
  per-machine. Per-user policy needs a different mechanism.
- The console is a single process with a single password. It is not multi-tenant
  and does not pretend to be.
