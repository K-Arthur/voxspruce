import dataclasses
import unittest

from tests import require_module


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.commands = require_module(self, "wayland_voice_control.commands")
        self.domain = require_module(self, "wayland_voice_control.domain")

    def test_catalogue_contains_only_the_nine_declared_actions(self):
        expected = {
            "next_field": ("next field", "Tab", False),
            "previous_field": ("previous field", "Shift+Tab", False),
            "copy": ("copy", "Ctrl+C", False),
            "paste": ("paste", "Ctrl+V", False),
            "undo": ("undo", "Ctrl+Z", False),
            "select_all": ("select all", "Ctrl+A", False),
            "press_enter": ("press enter", "Return", True),
            "close_window": ("close window", "Alt+F4", True),
            "delete_selection": ("delete selection", "Delete", True),
        }
        actual = {
            key: (
                command.phrase,
                command.key_chord,
                command.risk == self.domain.Risk.HIGH,
            )
            for key, command in self.commands.COMMANDS.items()
        }
        self.assertEqual(actual, expected)

    def test_matching_only_normalizes_case_and_whitespace(self):
        self.assertEqual(
            self.commands.match_command("  NeXt   FIELD ").id, "next_field"
        )
        self.assertEqual(
            self.commands.match_command("PREVIOUS\t FIELD").id, "previous_field"
        )

    def test_unknown_fuzzy_and_multiple_commands_are_rejected(self):
        for phrase in (
            "",
            "cop",
            "copy and paste",
            "copy; paste",
            "press enter please",
            "copy\npaste",
            "rm -rf /",
            "next_field",
        ):
            with (
                self.subTest(phrase=phrase),
                self.assertRaisesRegex(self.domain.DomainError, "Unknown command"),
            ):
                self.commands.match_command(phrase)

    def test_catalogue_and_entries_cannot_be_mutated(self):
        with self.assertRaises(TypeError):
            self.commands.COMMANDS["copy"] = None
        with self.assertRaises(dataclasses.FrozenInstanceError):
            self.commands.COMMANDS["copy"].key_chord = "Alt+F4"


if __name__ == "__main__":
    unittest.main()
