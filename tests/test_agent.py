"""Tests for the ros-agent side of the contract.

The agent and the console compile policy independently - the console to show a
preview, the agent to write the real file. These tests pin the two together so
the preview cannot drift away from what lands on disk.
"""

import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "packages", "ros-agent", "usr", "lib", "ros-agent"))
sys.path.insert(0, os.path.join(ROOT, "management", "console"))

import agent  # noqa: E402
from app import policy  # noqa: E402


class KeyfileTests(unittest.TestCase):
    def test_sections_and_keys_are_rendered(self):
        rendered = agent.render_dconf_keyfile(
            {
                "name": "Finance",
                "revision": 3,
                "dconf": {"org/gnome/desktop/interface": {"accent-color": "'teal'"}},
            }
        )
        self.assertIn("[org/gnome/desktop/interface]", rendered)
        self.assertIn("accent-color='teal'", rendered)
        self.assertIn("revision 3", rendered)

    def test_leading_slashes_are_stripped_from_sections(self):
        rendered = agent.render_dconf_keyfile(
            {"dconf": {"/org/gnome/shell/": {"disable-user-extensions": "false"}}}
        )
        self.assertIn("[org/gnome/shell]", rendered)

    def test_agent_and_console_render_identically(self):
        compiled = policy.compile_policy("Default", 1, policy.default_policy())
        self.assertEqual(
            agent.render_dconf_keyfile(compiled).strip(),
            policy.keyfile_preview(compiled).strip(),
        )


class InventoryTests(unittest.TestCase):
    def test_inventory_has_the_fields_the_console_displays(self):
        inventory = agent.collect_inventory()
        for field in (
            "hostname", "machine_id", "os_pretty", "kernel", "arch",
            "cpu_count", "memory_mb", "disk", "agent_version",
        ):
            self.assertIn(field, inventory)

    def test_machine_id_is_never_empty(self):
        self.assertTrue(agent.machine_id())


if __name__ == "__main__":
    unittest.main()
