#!/usr/bin/env python3
"""Isoko - the ROS Store.

Shows the application catalogue the management console publishes, and installs
from it. Installation goes through `pkexec ros-agent app install <slug>`, so
the store itself never runs as root and can only ever install something the
catalogue already lists.

"Isoko" is Kinyarwanda for market.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Dict, List

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

APP_ID = "rw.ros.Store"
CATALOGUE_PATH = os.environ.get(
    "ROS_CATALOGUE", "/var/cache/ros-agent/catalogue.json"
)
CATEGORY_ORDER = ["Internet", "Office", "Media", "Utilities", "System", "Other"]


# --------------------------------------------------------------------------- #
# Catalogue
# --------------------------------------------------------------------------- #
def read_catalogue() -> List[Dict[str, Any]]:
    """The catalogue as the agent last cached it.

    Read from the cache rather than from the server: the store runs as the
    person using the machine and has no device token, and a workstation with a
    flaky link should still be able to browse what it can install.
    """
    try:
        with open(CATALOGUE_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle).get("applications", [])
    except (OSError, ValueError):
        return []


def is_installed(app: Dict[str, Any]) -> bool:
    reference = app.get("reference", "")
    if not reference:
        return False

    if app.get("source") == "flatpak":
        result = subprocess.run(
            ["flatpak", "info", reference],
            capture_output=True, text=True, check=False,
        )
        return result.returncode == 0

    result = subprocess.run(
        ["dpkg-query", "-W", "-f=${Status}", reference],
        capture_output=True, text=True, check=False,
    )
    return "install ok installed" in result.stdout


# --------------------------------------------------------------------------- #
# Window
# --------------------------------------------------------------------------- #
class StoreWindow(Adw.ApplicationWindow):
    def __init__(self, application: Adw.Application) -> None:
        super().__init__(application=application, title="Isoko")
        self.set_default_size(820, 640)

        self.toasts = Adw.ToastOverlay()
        self.search_text = ""

        header = Adw.HeaderBar()
        title = Adw.WindowTitle(title="Isoko", subtitle="ROS Store")
        header.set_title_widget(title)

        self.search = Gtk.SearchEntry(placeholder_text="Search applications")
        self.search.set_hexpand(True)
        self.search.connect("search-changed", self.on_search)
        search_bar = Gtk.SearchBar(search_mode_enabled=True)
        search_bar.set_child(self.search)
        search_bar.connect_entry(self.search)

        refresh = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Refresh")
        refresh.connect("clicked", lambda _button: self.reload())
        header.pack_end(refresh)

        self.content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        scroller = Gtk.ScrolledWindow(vexpand=True)
        scroller.set_child(self.content)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(header)
        box.append(search_bar)
        box.append(scroller)

        self.toasts.set_child(box)
        self.set_content(self.toasts)

        self.reload()

    # ----------------------------------------------------------------- data --
    def reload(self) -> None:
        child = self.content.get_first_child()
        while child is not None:
            self.content.remove(child)
            child = self.content.get_first_child()

        applications = read_catalogue()
        if not applications:
            self.content.append(self.empty_state())
            return

        matching = [
            app for app in applications
            if self.search_text in (
                app.get("name", "") + app.get("tagline", "") +
                app.get("description", "") + app.get("category", "")
            ).lower()
        ]

        if not matching:
            self.content.append(
                Adw.StatusPage(
                    icon_name="system-search-symbolic",
                    title="Nothing found",
                    description="No application matches that search.",
                )
            )
            return

        page = Adw.PreferencesPage()
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for app in matching:
            by_category.setdefault(app.get("category", "Other"), []).append(app)

        for category in sorted(
            by_category,
            key=lambda name: (
                CATEGORY_ORDER.index(name) if name in CATEGORY_ORDER else 99, name
            ),
        ):
            group = Adw.PreferencesGroup(title=category)
            for app in sorted(by_category[category], key=lambda a: a.get("name", "")):
                group.add(self.application_row(app))
            page.add(group)

        self.content.append(page)

    def empty_state(self) -> Gtk.Widget:
        return Adw.StatusPage(
            icon_name="package-x-generic-symbolic",
            title="No applications yet",
            description=(
                "This machine has not received an application catalogue. "
                "It arrives from the ROS console when the machine syncs."
            ),
        )

    def application_row(self, app: Dict[str, Any]) -> Adw.ActionRow:
        installed = is_installed(app)

        subtitle = app.get("tagline", "")
        if app.get("upstream"):
            subtitle = "%s · built on %s" % (subtitle, app["upstream"])

        row = Adw.ActionRow(title=app.get("name", app.get("slug", "?")), subtitle=subtitle)
        row.add_prefix(
            Gtk.Image(
                icon_name=app.get("icon") or "application-x-executable-symbolic",
                pixel_size=32,
            )
        )

        if installed:
            if app.get("desktop_id"):
                open_button = Gtk.Button(label="Open", valign=Gtk.Align.CENTER)
                open_button.add_css_class("flat")
                open_button.connect("clicked", self.on_open, app)
                row.add_suffix(open_button)

            remove = Gtk.Button(label="Remove", valign=Gtk.Align.CENTER)
            remove.add_css_class("destructive-action")
            remove.connect("clicked", self.on_action, app, "remove")
            row.add_suffix(remove)
        else:
            install = Gtk.Button(label="Install", valign=Gtk.Align.CENTER)
            install.add_css_class("suggested-action")
            install.connect("clicked", self.on_action, app, "install")
            row.add_suffix(install)

        return row

    # -------------------------------------------------------------- actions --
    def on_search(self, entry: Gtk.SearchEntry) -> None:
        self.search_text = entry.get_text().strip().lower()
        self.reload()

    def on_open(self, _button: Gtk.Button, app: Dict[str, Any]) -> None:
        launcher = Gio.DesktopAppInfo.new(app["desktop_id"])
        if launcher is None:
            self.toast("%s is installed but has no launcher" % app["name"])
            return
        launcher.launch([], None)

    def on_action(self, button: Gtk.Button, app: Dict[str, Any], action: str) -> None:
        button.set_sensitive(False)
        button.set_label("Working…")

        def finished(process: Gio.Subprocess, result: Gio.AsyncResult) -> None:
            try:
                ok = process.wait_check_finish(result)
            except GLib.Error as error:
                ok = False
                message = error.message
            else:
                message = ""

            if ok:
                self.toast(
                    "%s %s" % (app["name"], "installed" if action == "install" else "removed")
                )
            else:
                self.toast("Could not %s %s. %s" % (action, app["name"], message))
            self.reload()

        # pkexec, not sudo: the authentication prompt belongs to polkit, and
        # the agent only accepts a catalogue slug, never a package name.
        process = Gio.Subprocess.new(
            ["pkexec", "/usr/bin/ros-agent", "app", action, app["slug"]],
            Gio.SubprocessFlags.NONE,
        )
        process.wait_check_async(None, finished)

    def toast(self, message: str) -> None:
        self.toasts.add_toast(Adw.Toast(title=message, timeout=4))


class StoreApplication(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self) -> None:
        window = self.props.active_window
        if window is None:
            window = StoreWindow(self)
        window.present()


def main() -> int:
    return StoreApplication().run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
