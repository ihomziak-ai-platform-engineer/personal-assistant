"""Text notes with stable IDs and normalized, deduplicated tags."""

from collections import UserDict
from collections.abc import Iterable

from personal_assistant.fields import Tag, clean_text


class Note:
    """A text note; duplicate titles are allowed, IDs are unique."""

    def __init__(
        self, note_id: int, title: str, text: str, tags: Iterable[str] = ()
    ) -> None:
        if type(note_id) is not int or note_id < 1:
            raise ValueError("ID нотатки має бути додатним цілим числом.")
        self.id = note_id
        self.title = clean_text(title, "Заголовок", 120)
        self.text = clean_text(text, "Текст", 10000)
        self.tags = {Tag(tag).value for tag in tags}

    def edit(self, title: str, text: str) -> None:
        # Validate both values before replacing either of them.
        title = clean_text(title, "Заголовок", 120)
        text = clean_text(text, "Текст", 10000)
        self.title, self.text = title, text

    def add_tags(self, tags: Iterable[str]) -> None:
        self.tags.update({Tag(tag).value for tag in tags})

    def remove_tag(self, tag: str) -> None:
        normalized = Tag(tag).value
        if normalized not in self.tags:
            raise ValueError("Цього тегу немає в нотатці.")
        self.tags.remove(normalized)

    def __str__(self) -> str:
        tags = ", ".join(f"#{tag}" for tag in sorted(self.tags)) or "немає"
        return f"[{self.id}] {self.title}\n  {self.text}\n  Теги: {tags}"


class NoteBook(UserDict[int, Note]):
    """Notes indexed by unique, increasing IDs."""

    def __init__(self) -> None:
        super().__init__()
        self.next_id = 1

    def add(self, title: str, text: str, tags: Iterable[str] = ()) -> Note:
        note = Note(self.next_id, title, text, tags)
        self.data[note.id] = note
        self.next_id += 1
        return note

    def require(self, note_id: int) -> Note:
        if type(note_id) is not int or note_id not in self.data:
            raise ValueError(f"Нотатку з ID {note_id} не знайдено.")
        return self.data[note_id]

    def delete(self, note_id: int) -> None:
        self.require(note_id)
        del self.data[note_id]

    def search(self, query: str) -> list[Note]:
        if not query.strip():
            raise ValueError("Пошуковий запит не може бути порожнім.")
        query = query.casefold().strip()
        return [
            note for note in self.sorted_notes()
            if query in note.title.casefold() or query in note.text.casefold()
        ]

    def by_tag(self, tag: str) -> list[Note]:
        normalized = Tag(tag).value
        return [n for n in self.sorted_notes() if normalized in n.tags]

    def sorted_notes(self) -> list[Note]:
        return sorted(self.data.values(), key=lambda note: note.id)

    def grouped_by_tag(self) -> list[tuple[str, list[Note]]]:
        """Alphabetic tag groups; a note can occur in several groups."""
        tags = sorted({
            tag for note in self.data.values() for tag in note.tags
        })
        groups = [(tag, self.by_tag(tag)) for tag in tags]
        untagged = [n for n in self.sorted_notes() if not n.tags]
        if untagged:
            groups.append(("без тегів", untagged))
        return groups
