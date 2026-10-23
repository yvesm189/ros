# Applications

ROS ships no third-party browser and no third-party office suite. It ships a
catalogue of ROS applications, a store to install them from, and a management
console that decides which of them a machine gets.

## Why

A workstation that boots into ROS branding and then opens Firefox is two
products pretending to be one. The moment a user opens the browser or a
document they are looking at somebody else's interface, somebody else's
settings dialogs, somebody else's update prompts.

So the basic application set is built on open source upstreams, packaged and
presented under ROS names, with the ROS interface font and ROS defaults.

## The catalogue

Names are Kinyarwanda and say what the application is for rather than who wrote
it, paired with a plain English descriptor — a dock tooltip and a tender
document want different things.

| ROS name | Means | Role | Built on | Installs |
|---|---|---|---|---|
| **Isoko** | market | The ROS Store itself | ROS | shipped |
| **Urubuga** | the web | Web browser | Firefox ESR | `firefox-esr` |
| **Inyandiko** | document | Documents, incl. `.docx` | LibreOffice Writer | `libreoffice-writer` |
| **Imibare** | numbers | Spreadsheets, incl. `.xlsx` | LibreOffice Calc | `libreoffice-calc` |
| **Imurika** | to display | Presentations, incl. `.pptx` | LibreOffice Impress | `libreoffice-impress` |
| **Umusomyi** | reader | PDF | Papers | `papers` |
| **Ubutumwa** | messages | Mail and calendar | Thunderbird | `thunderbird` |
| **Amashusho** | images | Photos | Loupe | `loupe` |
| **Injyana** | melody | Audio and video | Celluloid | `celluloid` |
| **Ububiko** | storage | Archives | File Roller | `file-roller` |
| **Ikarita** | map | Maps | GNOME Maps | `gnome-maps` |

Between Inyandiko, Imibare, Imurika and Umusomyi that is the same ground a
suite like WPS covers: Word, Excel, PowerPoint and PDF formats.

The catalogue is seeded from `management/console/app/catalogue.py` the first
time a console starts. After that it belongs to whoever runs the console —
editing the seed will not overwrite their catalogue or resurrect something they
deliberately removed.

## Adding an application from the console

**Applications** in the console is the catalogue editor. An entry needs:

| Field | What it is |
|---|---|
| ROS name | What the user sees — `Urubuga` |
| Identifier | Stable lowercase slug — `urubuga`. Policies and the store refer to this. |
| Tagline, description, category | The store listing |
| Built on | The open source upstream, shown so nobody has to guess |
| Install from | `apt` or `flatpak` |
| Reference | Package name or flatpak ref |
| Desktop file | Needed to pin it to the dock and to offer **Open** in the store |
| Icon | An icon name from the theme |

Unpublishing an entry hides it from the store without deleting it or disturbing
policies.

## Giving applications to machines

Open a policy group and tick the applications it should have. Saving publishes
a new revision; machines install what they are missing on their next sync, and
the group page prints exactly what they will act on.

**Nothing is ever uninstalled by a policy.** Removing an application from a
group means new machines will not get it. Taking software off a machine
somebody is using is a separate, destructive decision, and a sync timer is the
wrong thing to be making it.

## The ROS Store

`Isoko` is a GTK4 application on the workstation. It reads the catalogue the
agent cached at `/var/cache/ros-agent/catalogue.json`, so it works on a flaky
link, and shows what is installed by asking dpkg or flatpak directly.

It never runs as root. Install and remove go through:

```
pkexec /usr/bin/ros-agent app install <slug>
```

The agent takes a catalogue **slug**, never a package name, so the polkit
authorisation behind that prompt cannot be turned into "install anything".

```bash
ros-agent catalogue           # the catalogue, with install state, as JSON
ros-agent app install urubuga
ros-agent app remove urubuga
```

## Making an upstream look like ROS

`ros-app-defaults` carries the configuration that makes catalogue applications
behave like part of ROS. The files are inert until the application is installed,
so the package is safe on a machine that has none of them.

- **Fonts mostly come for free.** `ros-fonts` makes Funnel Display the generic
  `sans-serif` at the fontconfig level, so anything asking for a generic family
  already gets the brand face — including web pages.
- **Firefox needs one more push.** Its default for Western text is `serif`, and
  fonts cannot be set through `policies.json`: the Preferences policy only
  accepts a fixed list of pref prefixes and `font.` is not among them. The
  supported route is autoconfig, which is what `ros.cfg` is.
- **LibreOffice's interface needs nothing** — it uses the GTK VCL plugin, so
  menus and dialogs already follow the ROS font. What `ros.xcd` sets is the
  default font *inside new documents*, which comes from LibreOffice's own
  registry.

## What makes it a ROS application, not a reskin

1. **Ask fontconfig for a role, not a family.** `ROS UI` and `ROS Display` are
   aliases `ros-fonts` maps to the current brand faces. Hardcoding
   `Funnel Display` means rebuilding everything when the brand font changes.
2. **Take settings from dconf under `/org/ros/<app>/`**, so the console can push
   policy to the application the same way it pushes desktop policy — no new
   agent, no new protocol.
3. **Ship defaults as a dconf keyfile** in `/etc/dconf/db/ros.d/`, numbered
   above the desktop defaults and below `50-managed`, so the console can still
   override them.
4. **No telemetry and no update prompts of its own.** Updates are the fleet's
   job.
5. **Package it as `ros-app-<name>`** and depend on `ros-branding`, so a
   machine's application set is something apt can describe.

## Rebranding an upstream is not free

The part that gets underestimated:

- A **rebranded Firefox** means maintaining a build and tracking Mozilla's
  security releases within days of upstream, every cycle, forever. Mozilla's
  branding is trademarked, which is why Debian shipped Iceweasel for years. The
  honest first version — and what ships today — is Firefox with ROS policy, ROS
  fonts and a ROS name in the catalogue, not a fork.
- **LibreOffice** is a larger build still. Themed LibreOffice with ROS defaults
  is the realistic first step, not a new office suite.

Both are the right thing eventually. Neither is a weekend.
