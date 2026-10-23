# Applications

ROS ships no third-party browser and no third-party office suite. That is a
decision, not an omission.

## Why

A workstation that boots into ROS branding and then opens Firefox is two
products pretending to be one. The moment a user opens the browser or a
document, they are looking at somebody else's interface, somebody else's
settings dialogs, somebody else's update prompts and somebody else's idea of
what a toolbar should look like. Everything ROS does to the desktop stops at
the application window.

So the basic application set is being built as ROS applications, on open source
upstreams, carrying the ROS interface:

| Application | Upstream to build on | Status |
|---|---|---|
| Browser | Firefox / Chromium, rebuilt and themed | not started |
| Documents, sheets, slides | LibreOffice, or a lighter editor | not started |
| Mail | Thunderbird or Geary | not started |
| PDF, images, text, files, terminal | GNOME's own, already ROS-themed by dconf | shipped |

Until those exist, the image ships the GNOME system applications - Files, Text
Editor, Console, Settings - which already take ROS's theming through dconf, and
nothing else.

## What that means for the image now

- `base/live-build/config/package-lists/30-applications.list.chroot` carries
  utilities only: printing, scanning, remote support.
- The default dock pins Files, Text Editor, Console and Settings.
- There is no browser on a stock ROS image. That is deliberate and temporary.

If you need a browser on a machine today, install one - nothing stops you, and
`ros-desktop-base` does not conflict with it:

```bash
sudo apt install firefox-esr
```

Then pin it through the console rather than by editing the image: **Policies →
your group → Pinned applications**. That keeps the decision where it belongs,
with whoever runs the fleet, instead of baked into the ISO.

## What a ROS application has to do

When the first one lands, these are the things that make it a ROS application
rather than a rebranded upstream:

1. **Use the brand font by role, not by name.** Ask fontconfig for `ROS UI`;
   `ros-fonts` maps it to the current brand face. Hardcoding `Funnel Display`
   means every application has to be rebuilt when the brand font changes.
2. **Take its settings from dconf under `/org/ros/<app>/`**, so the management
   console can push policy to it the same way it pushes desktop policy - no new
   agent, no new protocol.
3. **Ship its own policy defaults as a dconf keyfile** in
   `/etc/dconf/db/ros.d/`, numbered above the desktop defaults and below
   `50-managed`, so the console can still override it.
4. **Carry no telemetry and no update prompts of its own.** Updates are the
   fleet's job.
5. **Be packaged as `ros-app-<name>`** and depend on `ros-branding`, so a
   machine's application set is something apt can describe.

## Rebranding an upstream is not free

Worth saying plainly, because it is the part that gets underestimated:

- A rebranded Firefox means maintaining a build, tracking security releases
  within days of upstream, and re-applying patches every cycle. Mozilla's
  branding is also trademarked - the reason Debian shipped Iceweasel for years.
  The cheap version is Firefox with an enterprise policy file and a ROS theme,
  not a fork.
- LibreOffice is a larger build still. The realistic first step is themed
  LibreOffice with ROS defaults, not a new office suite.

Both are the right thing to do eventually, and neither is a weekend. Starting
with the browser - the application people spend the day in - gets the most
visible return for the effort.
