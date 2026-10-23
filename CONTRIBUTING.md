# Contributing

ROS is small and early. The fastest way to be useful is to run it, find the
thing that does not work, and say precisely what you did.

## Getting set up

```bash
git clone https://github.com/yvesm189/ros.git
cd ros
make test        # should pass immediately, no containers needed
make console-dev # the console on http://127.0.0.1:8000
```

You do not need to build an ISO to work on ROS. `make agent-dev KEY=...` gives
you a real managed workstation in a container in about thirty seconds, and that
covers everything except the GNOME session itself.

## Before opening a pull request

```bash
make lint     # shell and Python syntax
make test     # unit tests
make check    # installs the packages on a clean Debian 13 and applies a policy
```

CI runs all three plus the console's API, so a green local run is a good
predictor.

## House style

**Code should read like the code around it.** Match the naming, the comment
density and the idioms already in the file you are editing.

**Comments explain why, not what.** `# compile the dconf database` above
`dconf update` is noise. `# keyfiles are inert until this runs` is the reason
the line exists.

**Shell**: `set -euo pipefail`, quote variables, prefer long flags in scripts.

**Python**: standard library only in `ros-agent` — it has to work on a minimal
image during a partial upgrade. The console may use its pinned dependencies.

**dconf**: values are GVariant text. Strings carry their own quotes; typed keys
carry their type (`uint32 600`). When in doubt, check the preview in the console
or run `dconf read` on the key.

## Things worth knowing

- The policy compiler exists twice — in the console to preview, in the agent to
  apply — and `tests/test_agent.py` asserts the two render identically. If you
  change one, change the other or the test will tell you.
- Everything a package ships under `etc/` becomes a conffile automatically, so
  a local edit survives an upgrade. Do not put generated files under `etc/`.
- Generated binaries do not go in git. The Plymouth logo PNG is produced from
  the SVG in the package's `postinst` for exactly this reason.
- Locks are expensive in support time. A pull request that adds one should say
  why the setting cannot be left to the user.

## Reporting a problem

Include the output of `ros-agent status`, the relevant part of
`journalctl -u ros-agent`, and what the console's preview said it was going to
write. Those three almost always locate the problem.
