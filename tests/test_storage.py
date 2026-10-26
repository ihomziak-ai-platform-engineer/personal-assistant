"""Persistence contracts, corruption handling and process exclusion."""

import os
import pickle
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from personal_assistant.contacts import Record
from personal_assistant.storage import (
    AssistantData,
    PickleStorage,
    StorageError,
    from_payload,
    to_payload,
)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)

    def sample(self):
        data = AssistantData()
        record = Record("Іван Петренко")
        record.add_phone("0501234567")
        record.set_email("ivan@example.com")
        record.set_address("Київ, вул. Миру 1")
        record.add_birthday("29.02.2000")
        data.contacts.add_record(record)
        data.notes.add(
            "Python", "Повторити декоратори", ["Навчання", "python"]
        )
        return data

    def test_roundtrip_preserves_all_data(self):
        data = self.sample()
        with PickleStorage(self.directory) as store:
            store.save(data)
        with PickleStorage(self.directory) as store:
            restored = store.load()
        self.assertEqual(to_payload(restored), to_payload(data))

    def test_deleted_note_id_stays_reserved_after_restart(self):
        data = self.sample()
        data.notes.delete(1)
        with PickleStorage(self.directory) as store:
            store.save(data)
            loaded = store.load()
            self.assertEqual(loaded.notes.add("New", "Text").id, 2)

    def test_missing_file_is_empty_and_read_does_not_write(self):
        with PickleStorage(self.directory) as store:
            self.assertEqual(len(store.load().contacts), 0)
            self.assertFalse(store.path.exists())

    def test_corrupt_file_is_preserved(self):
        for raw in (b"", b"not a pickle", b"\x80\x04truncated"):
            with self.subTest(raw=raw):
                path = self.directory / "data.pkl"
                path.write_bytes(raw)
                with PickleStorage(self.directory) as store:
                    with self.assertRaises(StorageError):
                        store.load()
                self.assertEqual(path.read_bytes(), raw)

    def test_pickle_globals_are_rejected(self):
        # Pickling a global reference does not execute it; loading must fail.
        (self.directory / "data.pkl").write_bytes(pickle.dumps(os.system))
        with PickleStorage(self.directory) as store:
            with self.assertRaises(StorageError):
                store.load()

    def test_trailing_bytes_are_rejected(self):
        raw = pickle.dumps(to_payload(self.sample())) + b"unexpected"
        (self.directory / "data.pkl").write_bytes(raw)
        with PickleStorage(self.directory) as store:
            with self.assertRaises(StorageError):
                store.load()

    def test_schema_version_and_next_id_are_checked(self):
        for key, value in (
            ("version", 99), ("version", True), ("next_note_id", 1),
            ("next_note_id", True), ("contacts", "bad"), ("notes", {}),
        ):
            payload = to_payload(self.sample())
            payload[key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    from_payload(payload)

    def test_duplicate_contacts_and_notes_are_rejected(self):
        for field in ("contacts", "notes"):
            payload = to_payload(self.sample())
            payload[field].append(deepcopy(payload[field][0]))
            with self.subTest(field=field), self.assertRaises(ValueError):
                from_payload(payload)

    def test_fields_are_revalidated_on_load(self):
        payload = to_payload(self.sample())
        payload["contacts"][0]["phones"] = ["invalid"]
        with self.assertRaises(ValueError):
            from_payload(payload)

    def test_failed_replace_keeps_original_and_cleans_temporary_file(self):
        with PickleStorage(self.directory) as store:
            store.save(self.sample())
            before = store.path.read_bytes()
            with patch("personal_assistant.storage.os.replace",
                       side_effect=OSError("disk failure")):
                with self.assertRaises(StorageError):
                    store.save(AssistantData())
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(list(self.directory.glob("*.tmp")), [])

    def test_size_limit_on_write(self):
        with PickleStorage(self.directory) as store:
            with patch("personal_assistant.storage.MAX_FILE_BYTES", 1):
                with self.assertRaises(StorageError):
                    store.save(self.sample())
            self.assertFalse(store.path.exists())

    def test_size_limit_on_read(self):
        with PickleStorage(self.directory) as store:
            store.save(self.sample())
            with patch("personal_assistant.storage.MAX_FILE_BYTES", 1):
                with self.assertRaises(StorageError):
                    store.load()

    def test_second_process_cannot_open_same_store(self):
        code = (
            "from pathlib import Path; import sys; "
            "from personal_assistant.storage import PickleStorage; "
            "PickleStorage(Path(sys.argv[1])).__enter__()"
        )
        with PickleStorage(self.directory):
            result = subprocess.run(
                [sys.executable, "-c", code, str(self.directory)],
                capture_output=True, text=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("StorageError", result.stderr)
        with PickleStorage(self.directory) as store:
            self.assertEqual(len(store.load().notes), 0)

    def test_storage_requires_session_lock(self):
        store = PickleStorage(self.directory)
        with self.assertRaises(RuntimeError):
            store.load()
        with self.assertRaises(RuntimeError):
            store.save(AssistantData())

    @unittest.skipIf(os.name == "nt", "POSIX permission bits only")
    def test_data_file_is_owner_only(self):
        with PickleStorage(self.directory) as store:
            store.save(self.sample())
            self.assertEqual(store.path.stat().st_mode & 0o777, 0o600)
