# Customising the desktop

Everything that makes a ROS machine look like ROS lives in
`packages/ros-branding/`. The package is a plain file tree: what you see in the
repository is what lands on the machine.

```
packages/ros-branding/
├── etc/
│   ├── dconf/
│   │   ├── profile/user              precedence: user, then site, then ROS
│   │   └── db/
│   │       ├── ros.d/                the ROS defaults  (00-interface … 40-peripherals)
│   │       │   └── locks/            keys a user may not change
│   │       ├── local.d/              left empty for the local administrator
│   │       └── gdm.d/                the login screen
│   ├── skel/.config/gtk-{3,4}.0/     accent colour for GTK applications
│   ├── firefox-esr/policies/         browser policy
│   └── chromium/policies/managed/
└── usr/share/
    ├── backgrounds/ros/              wallpapers, light and dark
    ├── pixmaps/                      logo, and the symbolic one GDM shows
    ├── gnome-background-properties/  makes the wallpaper appear in Settings
    └── plymouth/themes/ros/          boot splash
```

Rebuild and reinstall after any change:

```bash
make packages
# on a Debian machine or in `make agent-dev`:
sudo apt install ./out/packages/ros-branding_0.1.0_all.deb
```

## The palette

| Token | Value | Used for |
|---|---|---|
| ROS deep | `#06243A` | wallpaper base, splash background |
| ROS blue | `#0A79C7` | primary accent, logo badge, buttons |
| ROS blue light | `#2A93DD` | hover and focus |
| ROS gold | `#F7C948` | the single accent that is not blue |
| Surface | `#102434` | console UI panels |

The gold exists to keep the identity from being another blue Linux distribution.
Use it once per screen.

## Changing the defaults

Each file in `etc/dconf/db/ros.d/` is a dconf keyfile: `[section]` headers are
dconf paths without the leading slash, and values are **GVariant text**, which
is the part that trips people up.

```ini
[org/gnome/desktop/interface]
color-scheme='prefer-dark'      # a string needs its own quotes
accent-color='blue'
show-battery-percentage=true    # a boolean does not
font-name='Inter 11'

[org/gnome/desktop/session]
idle-delay=uint32 600           # this key is a uint32, and says so

[org/gnome/shell]
favorite-apps=['firefox-esr.desktop', 'org.gnome.Nautilus.desktop']
```

To find the key for something you changed in the GNOME UI:

```bash
dconf watch /          # then change the setting; the key and value print out
gsettings list-recursively org.gnome.desktop.interface
```

## Locks

`etc/dconf/db/ros.d/locks/ros-policy` lists dconf paths a user cannot change.
A locked key is enforced by GNOME at read time, not by something that runs
periodically and puts it back — the setting is simply not writable.

Keep the list short. Every lock is a support call. ROS locks the wallpaper, the
screen lock, telemetry, location and automatic updates, and nothing else.

## Accent colours

GNOME 47+ has a built-in accent colour, but it only accepts nine names:
`blue teal green yellow orange red pink purple slate`. An arbitrary brand hex is
not valid for that key.

So ROS does both:

- `accent-color='blue'` in dconf, for the shell and GNOME's own UI;
- `@define-color accent_bg_color #0A79C7;` in `etc/skel/.config/gtk-4.0/gtk.css`,
  for libadwaita applications, which gets the exact brand colour.

The `gtk.css` route only applies to users created *after* the package is
installed, because `/etc/skel` is copied at user creation. For existing users,
the dconf accent name is what takes effect.

## Wallpapers

`usr/share/backgrounds/ros/ros-{light,dark}.svg`. They are SVG on purpose:
one file, every resolution, no 4K PNGs in git. GNOME renders them through the
librsvg pixbuf loader, which is why `ros-branding` depends on
`librsvg2-common` — without it the background silently falls back to a colour.

Preview them without building anything:

```bash
make render        # writes out/render/wallpaper-{dark,light}.png
```

`usr/share/gnome-background-properties/ros.xml` is what makes the pair show up
in **Settings → Appearance** with automatic light/dark switching.

## Boot splash

`usr/share/plymouth/themes/ros/` holds a Plymouth script theme: a background
gradient, a centred logo, animated dots, and a password prompt for encrypted
disks.

The logo PNG is **generated**, not committed — the package's `postinst` runs
`rsvg-convert` on the SVG, then `plymouth-set-default-theme ros` and
`update-initramfs`. Plymouth's script module can only load raster images, and
keeping a generated PNG in version control means it drifts from the SVG.

To see the splash without rebooting a real machine:

```bash
sudo plymouthd --debug --tty=/dev/tty1 ; sudo plymouth --show-splash
sleep 10 ; sudo plymouth quit
```

## Login screen

`etc/dconf/db/gdm.d/01-ros-login` sets the GDM logo, the banner message and the
login screen's own colour scheme and clock. GDM reads its own dconf database,
which is why the login screen needs settings of its own rather than inheriting
the desktop's.

GDM's *background image* is not settable this way — it comes from the shell
theme. ROS leaves it alone rather than shipping a gresource fork that breaks on
the next GNOME release.

## The dock

ROS enables `dash-to-dock` and configures it in `20-shell`. The defaults are
chosen for people arriving from Windows: a bottom dock, auto-hide, dots under
running applications, and click-to-minimise.

```ini
[org/gnome/shell/extensions/dash-to-dock]
dock-position='BOTTOM'
dock-fixed=false
click-action='minimize-or-previews'
```

Window buttons are set in `00-interface` for the same reason:

```ini
[org/gnome/desktop/wm/preferences]
button-layout='appmenu:minimize,maximize,close'
```

This single key removes more "where did the button go" questions than anything
else in the image.

## Changing it for one group instead of everything

Anything above is the *default for every machine*. To change the look of one
department, do not edit this package: create a policy group in the console and
set it there. The console's form covers the common settings, and its
**Extra dconf** field covers everything else. See
[management.md](management.md).

Rule of thumb: the package is what ROS looks like; the console is what *your*
ROS looks like this week.
