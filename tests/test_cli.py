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

    def assert_rejected_without_changes(self, lines):
        before = to_payload(self.session.data)
        saves = len(self.repository.saves)
        for line in lines:
            with self.subTest(line=line):
                response = self.session.execute(line)
                self.assertTrue(response.message.startswith("Помилка:"))
                self.assertFalse(response.should_exit)
                self.assertEqual(to_payload(self.session.data), before)
                self.assertEqual(len(self.repository.saves), saves)

    def test_empty_fields_and_searches_do_not_change_existing_data(self):
        self.execute_ok('add Alice 0501234567 --email alice@example.com')
        self.execute_ok('note-add Title Text python')
        for value in ('""', '"   "'):
            self.assert_rejected_without_changes([
                f'add {value} 0671234567',
                f'add Bob {value}',
                f'add Bob --email {value}',
                f'add Bob --address {value}',
                f'add Bob --birthday {value}',
                f'rename Alice {value}',
                f'set-email Alice {value}',
                f'set-address Alice {value}',
                f'set-birthday Alice {value}',
                f'find {value}',
                f'note-add {value} Text',
                f'note-add Title {value}',
                f'note-edit 1 {value} Text',
                f'note-edit 1 Title {value}',
                f'note-find {value}',
                f'tag-add 1 {value}',
                f'tag-find {value}',
            ])

    def test_duplicate_contacts_and_phones_do_not_overwrite_data(self):
        self.execute_ok('add "Alice Brown" 0501234567')
        self.execute_ok('add "Alice Brown" 0671234567')
        self.execute_ok('add Bob 0631234567')
        self.assert_rejected_without_changes([
            'add "  ALICE   brown  "',
            'add "alice brown" 0501234567',
            'add "alice brown" --email other@example.com',
            'change "Alice Brown" 0501234567 0671234567',
            'rename "Alice Brown" BOB',
        ])
        self.execute_ok('add "alice brown" 0681234567')
        self.assertEqual(len(self.session.data.contacts), 2)
        record = self.session.data.contacts.require("Alice Brown")
        self.assertEqual(len(record.phones), 3)

    def test_duplicate_tags_are_ignored_and_invalid_batches_are_atomic(self):
        self.execute_ok('note-add Title Text Python #PYTHON')
        self.execute_ok('tag-add 1 python #Python study STUDY')
        self.assertEqual(self.session.data.notes.require(1).tags,
                         {"python", "study"})
        self.assert_rejected_without_changes([
            'tag-add 1 new "bad tag"',
            'note-add New Text valid "bad tag"',
            'note-edit 1 Changed ""',
            'tag-remove 1 missing',
        ])
        self.execute_ok('note-add New Text')
        self.assertEqual(self.session.data.notes.require(2).title, "New")

    def test_repeated_deletion_preserves_other_records(self):
        self.execute_ok('add Alice 0501234567')
        self.execute_ok('add Bob 0671234567')
        self.execute_ok('note-add First Text')
        self.execute_ok('note-add Second Text')
        self.execute_ok('delete Alice')
        self.execute_ok('note-delete 1')
        self.execute_ok('remove-phone Bob 0671234567')
        self.assert_rejected_without_changes([
            'delete Alice', 'note-delete 1', 'remove-phone Bob 0671234567',
        ])
        self.assertEqual(len(self.session.data.contacts), 1)
        self.assertEqual(self.session.data.notes.require(2).title, "Second")

    def test_missing_arguments_and_invalid_ids_allow_next_command(self):
        self.execute_ok('note-add Title Text')
        self.assert_rejected_without_changes([
            'add', 'show', 'change', 'rename', 'set-email', 'clear-field',
            'find', 'note-add', 'note-edit', 'note-delete', 'tag-add',
            'tag-remove', 'tag-find', 'note-show -1', 'note-show 1.5',
            'note-show 999999999999999999999999', 'help absent',
            'note-edit 999 New Text', 'clear-field Missing email',
        ])
        self.execute_ok('note-edit 1 Updated Text')
        self.assertEqual(self.session.data.notes.require(1).title, "Updated")

    def test_blank_lines_do_not_save_or_exit(self):
        for line in ('', ' ', '\t', '  \t  '):
            with self.subTest(line=line):
                response = self.session.execute(line)
                self.assertEqual(response.message, "")
                self.assertFalse(response.should_exit)
        self.assertEqual(self.repository.saves, [])

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
