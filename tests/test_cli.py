"""User-visible workflows, invalid input, save failures and real restarts."""

import io
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from personal_assistant.cli import Session, parse_input, run_loop
from personal_assistant.storage import AssistantData, StorageError, to_payload


class MemoryRepository:
    def __init__(self):
        self.saves = []
        self.fail = False

    def save(self, data):
        if self.fail:
            raise StorageError("test disk failure")
        self.saves.append(deepcopy(data))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.repository = MemoryRepository()
        self.session = Session(AssistantData(), self.repository)

    def execute_ok(self, line):
        response = self.session.execute(line)
        self.assertNotIn("Помилка:", response.message, response.message)
        return response

    def test_parser_supports_spaces_apostrophes_tags_and_empty_values(self):
        self.assertEqual(parse_input('AdD "Мар\'яна Петренко" 0501234567'),
                         ("add", ["Мар'яна Петренко", "0501234567"]))
        self.assertEqual(parse_input('note-add "" "Текст" #python'),
                         ("note-add", ["", "Текст", "#python"]))
        self.assertEqual(parse_input("add Мар'яна"), ("add", ["Мар'яна"]))

    def test_complete_contact_workflow(self):
        self.execute_ok(
            'add "Іван Петренко" 0501234567 --email ivan@example.com '
            '--address "Київ, вул. Миру 1" --birthday 03.01.1990'
        )
        self.execute_ok('add "іван петренко" 0671234567')
        self.execute_ok('change "Іван Петренко" 0501234567 0507654321')
        self.execute_ok('remove-phone "Іван Петренко" 0671234567')
        self.execute_ok('set-email "Іван Петренко" new@example.com')
        self.execute_ok('set-address "Іван Петренко" "Львів"')
        self.execute_ok('add-birthday "Іван Петренко" 04.01.1990')
        self.assertIn("04.01.1990", self.execute_ok(
            'show-birthday "Іван Петренко"'
        ).message)
        self.execute_ok('clear-field "Іван Петренко" email')
        self.execute_ok('rename "Іван Петренко" "Іван"')
        self.assertIn("0507654321", self.execute_ok('phone "Іван"').message)
        self.assertIn("Львів", self.execute_ok('find "ЛЬВІВ" address').message)
        self.assertIn("Іван", self.execute_ok("all").message)
        self.execute_ok('delete "Іван"')
        self.assertEqual(len(self.session.data.contacts), 0)

    def test_complete_note_workflow(self):
        self.execute_ok(
            'note-add "Python" "Повторити функції" python навчання'
        )
        self.execute_ok('tag-add 1 #PYTHON практика')
        self.execute_ok('note-edit 1 "Python ООП" "Повторити класи"')
        self.assertIn(
            "Python ООП", self.execute_ok('note-find "класи"').message
        )
        self.assertIn("Python ООП", self.execute_ok("tag-find python").message)
        self.assertIn("#навчання", self.execute_ok("note-show 1").message)
        self.assertIn("практика:", self.execute_ok("notes-sort").message)
        self.execute_ok("tag-remove 1 практика")
        self.execute_ok("note-delete 1")
        self.assertIn("немає", self.execute_ok("notes").message)

    def test_bad_input_does_not_change_state_or_stop_session(self):
        self.execute_ok('add "Іван" 0501234567')
        before = to_payload(self.session.data)
        count = len(self.repository.saves)
        for line in (
            'add "Unclosed', 'add "Олена" bad', 'change Іван bad 123',
            'set-email Іван invalid', 'rename Іван ""', 'delete Unknown',
            'birthdays -1', 'birthdays 367', 'birthdays abc',
            'birthdays 2 wrong', 'note-add "" "text"',
            'note-show 0', 'note-show nope', 'tag-find "bad tag"',
            'all extra', 'notes extra', 'exit extra', 'unknown',
            'add "Олена" --email a@example.com --email b@example.com',
            'add "Олена" --bad value', 'add "Олена" --address',
        ):
            with self.subTest(line=line):
                response = self.session.execute(line)
                self.assertTrue(response.message.startswith("Помилка:"))
                self.assertFalse(response.should_exit)
                self.assertEqual(to_payload(self.session.data), before)
                self.assertEqual(len(self.repository.saves), count)
        self.execute_ok('add "Олена" 0671234567')

    def test_save_failure_does_not_commit_in_memory(self):
        self.execute_ok('add "Іван" 0501234567')
        before = to_payload(self.session.data)
        self.repository.fail = True
        result = self.session.execute('delete "Іван"')
        self.assertTrue(result.message.startswith("Помилка:"))
        self.assertEqual(to_payload(self.session.data), before)
        self.repository.fail = False
        self.execute_ok('delete "Іван"')

    def test_reads_and_exit_do_not_rewrite_disk(self):
        for line in ("", "hello", "help", "help add", "all", "notes", "exit"):
            self.execute_ok(line)
        self.assertEqual(self.repository.saves, [])
        self.assertTrue(self.session.execute("close").should_exit)

    def test_partial_invalid_contact_is_not_created(self):
        result = self.session.execute(
            'add "Олена" 0501234567 --email bad --address "Київ"'
        )
        self.assertTrue(result.message.startswith("Помилка:"))
        self.assertEqual(len(self.session.data.contacts), 0)

    def test_eof_and_keyboard_interrupt_finish_loop(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error), patch(
                "builtins.input", side_effect=error
            ):
                with redirect_stdout(io.StringIO()) as output:
                    run_loop(self.session)
                self.assertIn("До побачення!", output.getvalue())

    def test_actual_restart_from_another_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            command = [sys.executable, "-m", "personal_assistant",
                       "--data-dir", str(data_dir)]
            first = subprocess.run(
                command,
                input='add "Іван" 0501234567\n'
                      'note-add "Python" "Текст" навчання\n',
                cwd=directory, text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            second = subprocess.run(
                command, input="all\nnotes\nexit\n", cwd=directory,
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("0501234567", second.stdout)
            self.assertIn("#навчання", second.stdout)

    def test_actual_cli_refuses_corrupt_store_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.pkl"
            path.write_bytes(b"corrupted")
            result = subprocess.run(
                [sys.executable, "-m", "personal_assistant",
                 "--data-dir", directory],
                input="exit\n", text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 1)
            self.assertEqual(path.read_bytes(), b"corrupted")
            self.assertIn("не перезаписано", result.stderr)
