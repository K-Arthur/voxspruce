import dataclasses
import unittest

from wayland_voice_control import commands
from wayland_voice_control.domain import DomainError, Risk


class CustomCommandTests(unittest.TestCase):
    def api(self):
        self.assertTrue(
            hasattr(commands, "CustomShortcut"), "Custom shortcuts are missing"
        )
        return commands.CustomShortcut

    def test_exact_custom_match_is_immutable_high_risk_and_disabled_is_unavailable(
        self,
    ):
        Shortcut = self.api()
        custom = Shortcut(
            "save", "  SAVE   Document ", "shift+ctrl+s", "Save current file"
        )
        catalogue = commands.command_catalogue((custom,))
        match = commands.match_command("save document", catalogue)
        self.assertEqual(
            (match.key_chord, match.description, match.risk, match.custom),
            ("Ctrl+Shift+S", "Save current file", Risk.HIGH, True),
        )
        self.assertEqual(custom.phrase, "save document")
        with self.assertRaises(TypeError):
            catalogue["save"] = None
        with self.assertRaises(dataclasses.FrozenInstanceError):
            custom.enabled = False
        with self.assertRaises(DomainError):
            commands.match_command(
                "save document",
                commands.command_catalogue(
                    (dataclasses.replace(custom, enabled=False),)
                ),
            )
        with self.assertRaises(DomainError):
            commands.match_command("save document please", catalogue)
        self.assertEqual(commands.match_command("copy", catalogue).id, "copy")

    def test_catalogue_rejects_collisions_duplicate_ids_and_size_over_100(self):
        Shortcut = self.api()
        first = Shortcut("save", "save file", "Ctrl+S")
        for items in (
            (first, Shortcut("other", "SAVE FILE", "Alt+S")),
            (first, Shortcut("save", "other phrase", "Alt+S")),
            (Shortcut("copy", "other phrase", "Alt+C"),),
            (Shortcut("other", "COPY", "Alt+C", enabled=False),),
            tuple(Shortcut(f"id{i}", f"phrase {i}", "A") for i in range(101)),
        ):
            with self.subTest(items=items), self.assertRaises(DomainError):
                commands.command_catalogue(items)

    def test_fields_reject_wrong_types_controls_and_oversize(self):
        Shortcut = self.api()
        for field, value in (
            ("id", ""),
            ("id", "x" * 65),
            ("id", "a;b"),
            ("phrase", ""),
            ("phrase", "x" * 121),
            ("phrase", "save\nfile"),
            ("phrase", "save\tfile"),
            ("phrase", "a\u202eb"),
            ("description", "x" * 241),
            ("description", "a\0b"),
            ("enabled", 1),
            ("enabled", None),
            ("key_chord", "Ctrl+S;rm"),
        ):
            data = {"id": "save", "phrase": "save file", "key_chord": "Ctrl+S"}
            data[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(DomainError):
                Shortcut(**data)

    def test_key_chords_are_single_validated_canonical_plans(self):
        self.assertTrue(
            hasattr(commands, "parse_key_chord"), "Safe chord parser is missing"
        )
        for chord, expected in [
            ("S", (ord("s"),)),
            ("Ctrl+S", (0xFFE3, ord("s"))),
            ("super+shift+alt+ctrl+F12", (0xFFE3, 0xFFE9, 0xFFE1, 0xFFEB, 0xFFC9)),
            ("Space", (32,)),
            ("PageDown", (0xFF56,)),
            ("BackSpace", (0xFF08,)),
        ]:
            self.assertEqual(commands.parse_key_chord(chord)[1], expected)
        for key in (
            "Return",
            "Tab",
            "Escape",
            "Delete",
            "Home",
            "End",
            "Left",
            "Right",
            "Up",
            "Down",
            "PageUp",
        ):
            self.assertEqual(len(commands.parse_key_chord(key)[1]), 1)
        for chord in (
            "Ctrl",
            "Ctrl+Ctrl+S",
            "Ctrl+S+T",
            "Ctrl+S,Ctrl+T",
            "XF86AudioMute",
            "0xff09",
            "Ctrl++",
            "Ctrl+;",
            "Ctrl+\nS",
            "Control+S",
            "",
            None,
            "F13",
            "é",
            "ſ",
        ):
            with self.subTest(chord=chord), self.assertRaises(DomainError):
                commands.parse_key_chord(chord)
