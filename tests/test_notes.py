"""Notes, tag normalization and stable identifiers."""

import unittest

from personal_assistant.notes import NoteBook


class NoteTests(unittest.TestCase):
    def setUp(self):
        self.book = NoteBook()

    def test_ids_are_not_reused_after_deletion(self):
        first = self.book.add("First", "Text")
        self.book.delete(first.id)
        self.assertEqual(self.book.add("Second", "Text").id, 2)

    def test_failed_creation_does_not_consume_an_id(self):
        with self.assertRaises(ValueError):
            self.book.add("", "Text")
        self.assertEqual(self.book.add("Title", "Text").id, 1)

    def test_edit_keeps_tags_and_validates_before_change(self):
        note = self.book.add("Old", "Text", ["Python"])
        with self.assertRaises(ValueError):
            note.edit("New", "")
        self.assertEqual(note.title, "Old")
        note.edit("New", "New text")
        self.assertEqual(note.tags, {"python"})

    def test_search_title_and_text(self):
        first = self.book.add("Python", "Декоратори")
        second = self.book.add("Навчання", "Python практика")
        self.assertEqual(self.book.search("PYTHON"), [first, second])
        self.assertEqual(self.book.search("декор"), [first])
        with self.assertRaises(ValueError):
            self.book.search(" ")

    def test_tags_are_normalized_and_exact_matches(self):
        note = self.book.add(
            "Title", "Text", ["Python", "#PYTHON", "навчання"]
        )
        self.assertEqual(note.tags, {"python", "навчання"})
        self.assertEqual(self.book.by_tag("#PYTHON"), [note])
        self.assertEqual(self.book.by_tag("py"), [])

    def test_invalid_bulk_tag_add_is_atomic(self):
        note = self.book.add("Title", "Text")
        with self.assertRaises(ValueError):
            note.add_tags(["valid", "bad tag"])
        self.assertEqual(note.tags, set())

    def test_tag_removal(self):
        note = self.book.add("Title", "Text", ["Python"])
        note.remove_tag("#PYTHON")
        self.assertEqual(note.tags, set())
        with self.assertRaises(ValueError):
            note.remove_tag("python")

    def test_sorted_tag_groups_and_untagged_last(self):
        both = self.book.add("Both", "Text", ["z", "a"])
        empty = self.book.add("Empty", "Text")
        self.assertEqual(self.book.grouped_by_tag(), [
            ("a", [both]), ("z", [both]), ("без тегів", [empty])
        ])

    def test_unknown_and_invalid_ids(self):
        self.book.add("Title", "Text")
        for value in (-1, 99, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.book.require(value)
