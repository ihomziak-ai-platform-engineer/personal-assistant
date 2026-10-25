"""Versioned pickle storage, atomic replacement and one local session lock.

Only primitive dictionaries/lists/strings/integers are serialized. Model
objects are reconstructed through their validators on every load.
"""

import io
import os
import pickle
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO

from personal_assistant.contacts import AddressBook, Record
from personal_assistant.notes import Note, NoteBook

MAX_FILE_BYTES = 10 * 1024 * 1024


class StorageError(Exception):
    """An actionable persistence failure that the CLI can display safely."""


@dataclass
class AssistantData:
    """Contact and note collections for a session."""

    contacts: AddressBook = field(default_factory=AddressBook)
    notes: NoteBook = field(default_factory=NoteBook)


class PrimitiveUnpickler(pickle.Unpickler):
    """Reject imports of functions/classes from a serialized payload.

    This narrows the supported format; it does not make arbitrary third-party
    pickle files trustworthy. Only load files created by this application.
    """

    def find_class(self, module: str, name: str) -> object:
        raise pickle.UnpicklingError("Об'єкти та функції у файлі заборонені.")


def to_payload(data: AssistantData) -> dict:
    """Use primitives to avoid coupling saved files to Python module paths."""
    return {
        "version": 1,
        "contacts": [
            {
                "name": str(record.name),
                "phones": [str(phone) for phone in record.phones],
                "address": str(record.address) if record.address else None,
                "email": str(record.email) if record.email else None,
                "birthday": str(record.birthday) if record.birthday else None,
            }
            for record in data.contacts.values()
        ],
        "notes": [
            {
                "id": note.id,
                "title": note.title,
                "text": note.text,
                "tags": sorted(note.tags),
            }
            for note in data.notes.sorted_notes()
        ],
        "next_note_id": data.notes.next_id,
    }


def require_shape(value: object, keys: set[str]) -> dict:
    """Validate the exact schema rather than silently discard unknown data."""
    if type(value) is not dict or set(value) != keys:
        raise ValueError("Неправильна структура збережених даних.")
    return value


def from_payload(payload: object) -> AssistantData:
    """Validate types, IDs, unique names and all field values on load."""
    root = require_shape(
        payload, {"version", "contacts", "notes", "next_note_id"}
    )
    if type(root["version"]) is not int or root["version"] != 1:
        raise ValueError("Непідтримувана версія даних.")
    if type(root["contacts"]) is not list or type(root["notes"]) is not list:
        raise ValueError("Контакти й нотатки повинні бути списками.")
    data = AssistantData()
    for raw in root["contacts"]:
        item = require_shape(
            raw, {"name", "phones", "address", "email", "birthday"}
        )
        record = Record(item["name"])
        if type(item["phones"]) is not list:
            raise ValueError("Телефони повинні бути списком.")
        for phone in item["phones"]:
            record.add_phone(phone)
        for key, setter in (
            ("address", record.set_address),
            ("email", record.set_email),
            ("birthday", record.add_birthday),
        ):
            if item[key] is not None:
                setter(item[key])
        data.contacts.add_record(record)
    for raw in root["notes"]:
        item = require_shape(raw, {"id", "title", "text", "tags"})
        if type(item["tags"]) is not list:
            raise ValueError("Теги повинні бути списком.")
        note = Note(item["id"], item["title"], item["text"], item["tags"])
        if note.id in data.notes:
            raise ValueError("Повторний ID нотатки у файлі.")
        data.notes[note.id] = note
    next_id = root["next_note_id"]
    if type(next_id) is not int or next_id <= max(data.notes, default=0):
        raise ValueError("Некоректний лічильник нотаток.")
    data.notes.next_id = next_id
    return data


class PickleStorage:
    """A context-managed repository for a local filesystem.

    The lock is held for the entire CLI session, so a second process cannot
    overwrite an older in-memory snapshot. OS locks are released on exit.
    """

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = (
            directory if directory is not None
            else Path.home() / ".personal_assistant"
        ).expanduser().resolve()
        self.path = self.directory / "data.pkl"
        self._lock_file: BinaryIO | None = None

    def __enter__(self) -> "PickleStorage":
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(
                self.directory / "data.lock", os.O_RDWR | os.O_CREAT, 0o600
            )
            self._lock_file = os.fdopen(descriptor, "r+b")
            if os.name == "nt":
                import msvcrt

                self._lock_file.seek(0, os.SEEK_END)
                if self._lock_file.tell() == 0:
                    self._lock_file.write(b"0")
                    self._lock_file.flush()
                self._lock_file.seek(0)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if self._lock_file is not None:
                self._lock_file.close()
                self._lock_file = None
            raise StorageError(
                "Не вдалося відкрити сховище: перевірте права доступу "
                "та закрийте інший запущений помічник."
            ) from exc
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    def _require_lock(self) -> None:
        if self._lock_file is None:
            raise RuntimeError("Use PickleStorage inside a with statement.")

    def load(self) -> AssistantData:
        self._require_lock()
        try:
            with self.path.open("rb") as source:
                raw = source.read(MAX_FILE_BYTES + 1)
        except FileNotFoundError:
            return AssistantData()
        except OSError as exc:
            raise StorageError("Не вдалося прочитати файл даних.") from exc
        if len(raw) > MAX_FILE_BYTES:
            raise StorageError("Файл даних перевищує ліміт 10 MiB.")
        try:
            stream = io.BytesIO(raw)
            payload = PrimitiveUnpickler(stream).load()
            if stream.read(1):
                raise ValueError("Зайві байти після збережених даних.")
            return from_payload(payload)
        except (
            pickle.PickleError, EOFError, ValueError, TypeError,
            AttributeError, KeyError, OverflowError, RecursionError,
        ) as exc:
            raise StorageError(
                "Файл даних пошкоджений або має несумісний формат. "
                "Його не перезаписано; відновіть власну резервну копію."
            ) from exc

    def save(self, data: AssistantData) -> None:
        self._require_lock()
        raw = pickle.dumps(to_payload(data), protocol=4)
        if len(raw) > MAX_FILE_BYTES:
            raise StorageError("Дані перевищують ліміт 10 MiB.")
        temporary: Path | None = None
        try:
            # Same directory guarantees that replacement stays on one volume.
            with tempfile.NamedTemporaryFile(
                dir=self.directory, prefix="data-", suffix=".tmp", delete=False
            ) as target:
                temporary = Path(target.name)
                target.write(raw)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        except OSError as exc:
            raise StorageError(
                "Не вдалося зберегти зміни. Перевірте права доступу "
                "та вільне місце. Команду не застосовано."
            ) from exc
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
