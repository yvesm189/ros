"""Tests for the console's policy compiler.

These run without a database, a server or a Debian machine, which is the whole
point: policy compilation is the part that must never be wrong, because its
output is written to every workstation in the fleet.
"""

import os
import sys
import unittest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "management", "console")
)

from app import policy  # noqa: E402


class CompileTests(unittest.TestCase):
    def test_defaults_compile_to_expected_sections(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        self.assertEqual(compiled["name"], "Default")
        self.assertEqual(compiled["revision"], 1)
        self.assertIn("org/gnome/desktop/interface", compiled["dconf"])
        self.assertIn("org/gnome/shell", compiled["dconf"])

    def test_strings_are_gvariant_quoted(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        interface = compiled["dconf"]["org/gnome/desktop/interface"]
        self.assertEqual(interface["accent-color"], "'blue'")
        self.assertEqual(interface["show-battery-percentage"], "true")

    def test_idle_delay_carries_its_uint32_type(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        self.assertEqual(
            compiled["dconf"]["org/gnome/desktop/session"]["idle-delay"], "uint32 600"
        )

    def test_quotes_in_values_are_escaped(self):
        self.assertEqual(policy.gv_string("it's"), r"'it\'s'")

    def test_extra_dconf_overrides_the_form(self):
        stored = policy.default_policy()
        stored["extra_dconf"] = {
            "org/gnome/desktop/interface": {"accent-color": "'purple'"}
        }
        compiled = policy.compile_policy("Default", 2, stored)
        self.assertEqual(
            compiled["dconf"]["org/gnome/desktop/interface"]["accent-color"], "'purple'"
        )


class BrandDefaultTests(unittest.TestCase):
    """The defaults are the brand, so they are worth pinning."""

    def test_interface_font_is_the_brand_font(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        interface = compiled["dconf"]["org/gnome/desktop/interface"]
        self.assertEqual(interface["font-name"], "'Funnel Display 11'")
        self.assertEqual(interface["document-font-name"], "'Funnel Display 11'")

    def test_no_third_party_applications_are_pinned(self):
        favourites = policy.DEFAULT_SETTINGS["favorites"]
        for unwanted in ("firefox", "libreoffice", "thunderbird", "chrome"):
            self.assertFalse(
                any(unwanted in app.lower() for app in favourites),
                "%s should not be pinned: ROS ships its own applications" % unwanted,
            )

    def test_pinned_applications_look_like_desktop_ids(self):
        for app in policy.DEFAULT_SETTINGS["favorites"]:
            self.assertTrue(app.endswith(".desktop"), app)


class ApplicationTests(unittest.TestCase):
    def test_applications_are_carried_into_the_compiled_policy(self):
        apps = [{"slug": "urubuga", "name": "Urubuga",
                 "source": "apt", "reference": "firefox-esr"}]
        compiled = policy.compile_policy("Default", 1, policy.default_policy(), apps)
        self.assertEqual(compiled["applications"], apps)

    def test_no_applications_by_default(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        self.assertEqual(compiled["applications"], [])

    def test_form_collects_ticked_applications(self):
        result = policy.policy_from_form(
            {"application:urubuga": "on", "application:inyandiko": "on",
             "application:imibare": ""}
        )
        self.assertEqual(result["applications"], ["inyandiko", "urubuga"])

    def test_summary_is_readable_when_empty(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        self.assertIn("No applications", policy.application_summary(compiled))


class CommandTests(unittest.TestCase):
    """The allowlist is the whole of what a user can do as root, so it is
    worth pinning that it parses the way an administrator expects."""

    def test_name_command_and_description(self):
        commands = policy.commands_from_text(
            "restart-printing = systemctl restart cups  # Restart printing"
        )
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["name"], "restart-printing")
        self.assertEqual(commands[0]["argv"], ["systemctl", "restart", "cups"])
        self.assertEqual(commands[0]["description"], "Restart printing")

    def test_commands_are_argument_lists_not_shell_strings(self):
        commands = policy.commands_from_text("logs = journalctl --since -1h")
        self.assertIsInstance(commands[0]["argv"], list)
        self.assertEqual(commands[0]["argv"], ["journalctl", "--since", "-1h"])

    def test_quoted_arguments_survive(self):
        commands = policy.commands_from_text("note = logger 'disk check run'")
        self.assertEqual(commands[0]["argv"], ["logger", "disk check run"])

    def test_malformed_lines_are_dropped_not_raised(self):
        commands = policy.commands_from_text(
            "good = true\nno equals here\n# a comment\n\nbad = 'unclosed"
        )
        self.assertEqual([c["name"] for c in commands], ["good"])

    def test_no_commands_by_default(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        self.assertEqual(compiled["commands"], [])
        self.assertIn("No elevated commands", policy.command_summary(compiled))

    def test_round_trip_through_the_textarea(self):
        text = "restart-printing = systemctl restart cups  # Restart the print service"
        commands = policy.commands_from_text(text)
        self.assertEqual(
            policy.commands_from_text(policy.commands_to_text(commands)), commands
        )


class CatalogueTests(unittest.TestCase):
    def test_seed_entries_are_complete(self):
        from app import catalogue

        slugs = set()
        for app in catalogue.seed():
            for field in ("slug", "name", "tagline", "category", "source", "reference"):
                self.assertTrue(app.get(field), "%s missing %s" % (app, field))
            self.assertIn(app["source"], ("apt", "flatpak"))
            self.assertNotIn(app["slug"], slugs, "duplicate slug")
            slugs.add(app["slug"])

    def test_catalogue_covers_the_office_formats(self):
        from app import catalogue

        taglines = " ".join(a["tagline"].lower() for a in catalogue.seed())
        for need in ("browser", "documents", "spreadsheets", "presentations", "pdf"):
            self.assertIn(need, taglines)


class FormTests(unittest.TestCase):
    def test_invalid_choices_fall_back_to_defaults(self):
        result = policy.policy_from_form(
            {"accent_color": "neon", "dock_position": "SOMEWHERE"}
        )
        self.assertEqual(result["settings"]["accent_color"], "blue")
        self.assertEqual(result["settings"]["dock_position"], "BOTTOM")

    def test_icon_size_is_clamped(self):
        self.assertEqual(
            policy.policy_from_form({"dock_icon_size": "9999"})["settings"]["dock_icon_size"],
            128,
        )
        self.assertEqual(
            policy.policy_from_form({"dock_icon_size": "nonsense"})["settings"]["dock_icon_size"],
            40,
        )

    def test_lists_accept_newlines_or_commas(self):
        by_line = policy.policy_from_form({"favorites": "a.desktop\nb.desktop"})
        by_comma = policy.policy_from_form({"favorites": "a.desktop, b.desktop"})
        self.assertEqual(by_line["settings"]["favorites"], ["a.desktop", "b.desktop"])
        self.assertEqual(by_comma["settings"]["favorites"], ["a.desktop", "b.desktop"])

    def test_unchecked_boxes_mean_false(self):
        result = policy.policy_from_form({})
        self.assertFalse(result["settings"]["lock_enabled"])
        self.assertFalse(result["settings"]["dock_fixed"])

    def test_malformed_extra_dconf_is_ignored_not_raised(self):
        result = policy.policy_from_form({"extra_dconf": "{not json"})
        self.assertEqual(result["extra_dconf"], {})


if __name__ == "__main__":
    unittest.main()
