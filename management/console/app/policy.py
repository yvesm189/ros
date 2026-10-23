"""Desktop policy model.

A policy is stored in the friendly shape the console UI edits, and compiled
into the dconf keyfile shape the agent applies. Keeping the two apart means an
administrator never has to type GVariant syntax, while anything the form does
not cover can still be expressed as raw dconf in `extra_dconf`.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

# GNOME only accepts these accent names; an arbitrary hex value is not valid
# for org.gnome.desktop.interface accent-color.
ACCENT_COLORS = [
    "blue", "teal", "green", "yellow", "orange", "red", "pink", "purple", "slate",
]
COLOR_SCHEMES = ["default", "prefer-dark", "prefer-light"]
DOCK_POSITIONS = ["BOTTOM", "LEFT", "RIGHT", "TOP"]

DEFAULT_SETTINGS: Dict[str, Any] = {
    "color_scheme": "prefer-dark",
    "accent_color": "blue",
    "font_name": "Inter 11",
    "clock_format": "24h",
    "show_battery_percentage": True,
    "wallpaper_light": "file:///usr/share/backgrounds/ros/ros-light.svg",
    "wallpaper_dark": "file:///usr/share/backgrounds/ros/ros-dark.svg",
    "dock_position": "BOTTOM",
    "dock_fixed": False,
    "dock_icon_size": 40,
    "favorites": [
        "firefox-esr.desktop",
        "org.gnome.Nautilus.desktop",
        "libreoffice-writer.desktop",
        "libreoffice-calc.desktop",
        "org.gnome.Settings.desktop",
    ],
    "extensions": [
        "dash-to-dock@micxgx.gmail.com",
        "appindicatorsupport@rgcjonas.gmail.com",
    ],
    "lock_enabled": True,
    "idle_delay": 600,
}

DEFAULT_LOCKS: List[str] = [
    "/org/gnome/desktop/background/picture-uri",
    "/org/gnome/desktop/background/picture-uri-dark",
    "/org/gnome/desktop/screensaver/lock-enabled",
]


def default_policy() -> Dict[str, Any]:
    return {
        "settings": dict(DEFAULT_SETTINGS),
        "extra_dconf": {},
        "locks": list(DEFAULT_LOCKS),
    }


# --------------------------------------------------------------------------- #
# GVariant text helpers
# --------------------------------------------------------------------------- #
def gv_string(value: str) -> str:
    return "'%s'" % str(value).replace("\\", "\\\\").replace("'", "\\'")


def gv_bool(value: Any) -> str:
    return "true" if value else "false"


def gv_int(value: Any) -> str:
    return str(int(value))


def gv_uint32(value: Any) -> str:
    return "uint32 %d" % int(value)


def gv_strv(values: List[str]) -> str:
    return "[%s]" % ", ".join(gv_string(v) for v in values if str(v).strip())


# --------------------------------------------------------------------------- #
# Compilation
# --------------------------------------------------------------------------- #
def compile_dconf(policy: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """Turn stored policy settings into dconf sections the agent can write."""
    settings = dict(DEFAULT_SETTINGS)
    settings.update(policy.get("settings") or {})

    dconf: Dict[str, Dict[str, str]] = {
        "org/gnome/desktop/interface": {
            "color-scheme": gv_string(settings["color_scheme"]),
            "accent-color": gv_string(settings["accent_color"]),
            "font-name": gv_string(settings["font_name"]),
            "document-font-name": gv_string(settings["font_name"]),
            "clock-format": gv_string(settings["clock_format"]),
            "show-battery-percentage": gv_bool(settings["show_battery_percentage"]),
        },
        "org/gnome/desktop/background": {
            "picture-uri": gv_string(settings["wallpaper_light"]),
            "picture-uri-dark": gv_string(settings["wallpaper_dark"]),
            "picture-options": gv_string("zoom"),
        },
        "org/gnome/desktop/screensaver": {
            "lock-enabled": gv_bool(settings["lock_enabled"]),
            "picture-uri": gv_string(settings["wallpaper_dark"]),
        },
        "org/gnome/desktop/session": {
            "idle-delay": gv_uint32(settings["idle_delay"]),
        },
        "org/gnome/shell": {
            "favorite-apps": gv_strv(settings["favorites"]),
            "enabled-extensions": gv_strv(settings["extensions"]),
        },
        "org/gnome/shell/extensions/dash-to-dock": {
            "dock-position": gv_string(settings["dock_position"]),
            "dock-fixed": gv_bool(settings["dock_fixed"]),
            "dash-max-icon-size": gv_int(settings["dock_icon_size"]),
        },
    }

    # Raw dconf last: an explicit override always wins over the form.
    for section, keys in (policy.get("extra_dconf") or {}).items():
        dconf.setdefault(section.strip("/"), {}).update(keys)

    return dconf


def compile_policy(name: str, revision: int, policy: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "name": name,
        "revision": revision,
        "dconf": compile_dconf(policy),
        "locks": policy.get("locks") or [],
    }


# --------------------------------------------------------------------------- #
# Form handling
# --------------------------------------------------------------------------- #
def _lines(value: str) -> List[str]:
    """Accept either a newline or comma separated list from a textarea."""
    if not value:
        return []
    raw = value.replace(",", "\n").splitlines()
    return [item.strip() for item in raw if item.strip()]


def policy_from_form(form: Dict[str, Any]) -> Dict[str, Any]:
    """Build a stored policy from the console's edit form.

    Unknown or malformed values fall back to the ROS default rather than
    raising: a policy that is pushed to every workstation in the fleet is not
    the place for a stack trace.
    """
    def pick(field: str, allowed: List[str]) -> str:
        value = str(form.get(field, "")).strip()
        return value if value in allowed else DEFAULT_SETTINGS[field]

    try:
        icon_size = max(16, min(128, int(form.get("dock_icon_size", 40))))
    except (TypeError, ValueError):
        icon_size = DEFAULT_SETTINGS["dock_icon_size"]

    try:
        idle_delay = max(0, int(form.get("idle_delay", 600)))
    except (TypeError, ValueError):
        idle_delay = DEFAULT_SETTINGS["idle_delay"]

    extra_raw = str(form.get("extra_dconf", "")).strip()
    try:
        extra = json.loads(extra_raw) if extra_raw else {}
        if not isinstance(extra, dict):
            extra = {}
    except ValueError:
        extra = {}

    return {
        "settings": {
            "color_scheme": pick("color_scheme", COLOR_SCHEMES),
            "accent_color": pick("accent_color", ACCENT_COLORS),
            "font_name": str(form.get("font_name") or DEFAULT_SETTINGS["font_name"]),
            "clock_format": pick("clock_format", ["24h", "12h"]),
            "show_battery_percentage": bool(form.get("show_battery_percentage")),
            "wallpaper_light": str(
                form.get("wallpaper_light") or DEFAULT_SETTINGS["wallpaper_light"]
            ),
            "wallpaper_dark": str(
                form.get("wallpaper_dark") or DEFAULT_SETTINGS["wallpaper_dark"]
            ),
            "dock_position": pick("dock_position", DOCK_POSITIONS),
            "dock_fixed": bool(form.get("dock_fixed")),
            "dock_icon_size": icon_size,
            "favorites": _lines(str(form.get("favorites", ""))),
            "extensions": _lines(str(form.get("extensions", ""))),
            "lock_enabled": bool(form.get("lock_enabled")),
            "idle_delay": idle_delay,
        },
        "extra_dconf": extra,
        "locks": _lines(str(form.get("locks", ""))),
    }


def keyfile_preview(compiled: Dict[str, Any]) -> str:
    """The exact file the agent will write, shown in the UI before saving."""
    lines = [
        "# Managed by ros-agent. Local edits are overwritten on every sync.",
        "# Policy: %s (revision %s)" % (compiled["name"], compiled["revision"]),
        "",
    ]
    for section in sorted(compiled["dconf"]):
        lines.append("[%s]" % section)
        for key in sorted(compiled["dconf"][section]):
            lines.append("%s=%s" % (key, compiled["dconf"][section][key]))
        lines.append("")
    return "\n".join(lines)
