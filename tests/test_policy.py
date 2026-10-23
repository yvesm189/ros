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
