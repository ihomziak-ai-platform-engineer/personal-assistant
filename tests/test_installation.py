"""Run the installed console command from outside the source directory."""

import os
import subprocess
import sysconfig
import tempfile
import unittest
from pathlib import Path

from personal_assistant import __version__
from personal_assistant.storage import PickleStorage


class InstallationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.data_dir = self.directory / "data"
        name = "personal-assistant.exe" if os.name == "nt" else (
            "personal-assistant"
        )
        self.executable = Path(sysconfig.get_path("scripts")) / name
        self.assertTrue(self.executable.is_file(), "Install the package first")

    def run_cli(self, commands="", *options):
        result = subprocess.run(
            [str(self.executable), "--data-dir", str(self.data_dir), *options],
            input=commands, cwd=self.directory, encoding="utf-8",
            env={**os.environ, "PYTHONUTF8": "1"}, capture_output=True,
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return result.stdout

    def test_version_and_help_work_outside_project(self):
        self.assertEqual(self.run_cli("", "--version").strip(), __version__)
        self.assertIn("--data-dir", self.run_cli("", "--help"))
        self.assertFalse(self.data_dir.exists())

    def test_invalid_input_recovers_and_persists_after_restart(self):
        invalid = [
            'add "" 0501234567',
            'add Bob invalid',
            'add Bob --email invalid',
            'add alice 0501234567',
            'set-email Alice invalid',
            'rename Alice ""',
            'add "Unclosed',
            'note-edit 1 Changed ""',
            'tag-add 1 valid "bad tag"',
            'note-show -1',
            'birthdays -1',
            'unknown',
        ]
        lines = [
            'add Alice 0501234567 --email alice@example.com',
            'note-add Title Original python',
            *invalid,
            'add Bob 0671234567',
            'note-add Second Text',
            'exit',
        ]
        output = self.run_cli("\n".join(lines) + "\n")
        self.assertEqual(output.count("Помилка:"), len(invalid), output)
        restarted = self.run_cli("all\nnotes\nexit\n")
        self.assertNotIn("Помилка:", restarted)
        self.assertIn("alice@example.com", restarted)
        self.assertIn("0671234567", restarted)
        with PickleStorage(self.data_dir) as store:
            saved = store.load()
        self.assertEqual(len(saved.contacts), 2)
        alice = saved.contacts.require("Alice")
        self.assertEqual([str(p) for p in alice.phones], ["0501234567"])
        self.assertEqual(str(alice.email), "alice@example.com")
        first = saved.notes.require(1)
        self.assertEqual((first.title, first.text), ("Title", "Original"))
        self.assertEqual(first.tags, {"python"})
        self.assertEqual(saved.notes.require(2).title, "Second")
        self.assertEqual(saved.notes.next_id, 3)

    def test_readme_example_saves_contacts_and_notes(self):
        readme = Path(__file__).resolve().parents[1] / "README.md"
        section = readme.read_text(encoding="utf-8").split(
            "## Quick start\n", 1
        )[1]
        commands = section.split("```text\n", 1)[1].split("```", 1)[0]
        self.assertNotIn("Помилка:", self.run_cli(commands))
        with PickleStorage(self.data_dir) as store:
            saved = store.load()
        self.assertEqual(len(saved.contacts), 1)
        alice = saved.contacts.require("Alice Brown")
        self.assertEqual([str(p) for p in alice.phones],
                         ["0501234567", "0671234567"])
        self.assertEqual(str(alice.email), "alice@example.com")
        note = saved.notes.require(1)
        self.assertEqual(note.text, "Review classes and decorators")
        self.assertEqual(note.tags, {"python", "study", "practice"})
