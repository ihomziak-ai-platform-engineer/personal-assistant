"""Contacts, duplicate handling, search, and calendar edge cases."""

import unittest
from datetime import date

from personal_assistant.contacts import AddressBook, Record


class ContactTests(unittest.TestCase):
    def setUp(self):
        self.book = AddressBook()
        self.record = Record("Іван Петренко")
        self.record.add_phone("0501234567")
        self.record.set_email("ivan@example.com")
        self.record.set_address("Львів, вул. Миру 1")
        self.record.add_birthday("03.01.1990")
        self.book.add_record(self.record)

    def test_case_insensitive_find_and_duplicate_protection(self):
        self.assertIs(self.book.find("  ІВАН   Петренко "), self.record)
        with self.assertRaises(ValueError):
            self.book.add_record(Record("іван петренко"))
        self.assertEqual(len(self.book), 1)

    def test_phone_changes_are_validated_before_mutation(self):
        with self.assertRaises(ValueError):
            self.record.edit_phone("0501234567", "bad")
        self.assertIsNotNone(self.record.find_phone("0501234567"))
        with self.assertRaises(ValueError):
            self.record.add_phone("0501234567")
        self.record.add_phone("0671234567")
        with self.assertRaises(ValueError):
            self.record.edit_phone("0501234567", "0671234567")

    def test_phone_removal_and_missing_phone(self):
        self.record.remove_phone("0501234567")
        self.assertEqual(self.record.phones, [])
        with self.assertRaises(ValueError):
            self.record.remove_phone("0501234567")

    def test_rename_updates_key_without_losing_data(self):
        self.book.rename("Іван Петренко", "Іван Петрович")
        self.assertIsNone(self.book.find("Іван Петренко"))
        self.assertIs(self.book.find("Іван Петрович"), self.record)
        self.assertEqual(str(self.record.email), "ivan@example.com")

    def test_rename_cannot_overwrite_another_contact(self):
        self.book.add_record(Record("Олена"))
        with self.assertRaises(ValueError):
            self.book.rename("Іван Петренко", "олена")
        self.assertEqual(len(self.book), 2)
        self.assertIs(self.book.find("Іван Петренко"), self.record)

    def test_search_every_field_and_case(self):
        for field, query in (
            ("name", "ІВАН"), ("phone", "50123"), ("email", "EXAMPLE"),
            ("address", "ЛЬВІВ"), ("birthday", "03.01"), ("all", "Миру"),
        ):
            with self.subTest(field=field):
                self.assertEqual(self.book.search(query, field), [self.record])
        self.assertEqual(self.book.search("not found"), [])
        with self.assertRaises(ValueError):
            self.book.search("", "all")
        with self.assertRaises(ValueError):
            self.book.search("query", "wrong")

    def test_delete_reports_missing_contact(self):
        self.book.delete("Іван Петренко")
        self.assertEqual(len(self.book), 0)
        with self.assertRaises(ValueError):
            self.book.delete("Іван Петренко")

    def test_birthday_window_crosses_new_year(self):
        result = self.book.get_upcoming_birthdays(5, today=date(2026, 12, 29))
        self.assertEqual(result[0][1:], (date(2027, 1, 3), 5))

    def test_birthday_window_includes_today_and_boundary(self):
        result = self.book.get_upcoming_birthdays(0, today=date(2026, 1, 3))
        self.assertEqual(result[0][2], 0)
        self.assertEqual(
            self.book.get_upcoming_birthdays(1, today=date(2026, 1, 1)), []
        )

    def test_exact_means_target_date_even_one_year_ahead(self):
        result = self.book.get_upcoming_birthdays(
            365, today=date(2026, 1, 3), exact=True
        )
        self.assertEqual(result[0][1], date(2027, 1, 3))
        self.assertEqual(self.book.get_upcoming_birthdays(
            4, today=date(2026, 12, 29), exact=True
        ), [])

    def test_leap_birthday_policy(self):
        self.record.add_birthday("29.02.2000")
        nonleap = self.book.get_upcoming_birthdays(1, today=date(2027, 2, 27))
        leap = self.book.get_upcoming_birthdays(1, today=date(2028, 2, 28))
        self.assertEqual(nonleap[0][1], date(2027, 2, 28))
        self.assertEqual(leap[0][1], date(2028, 2, 29))

    def test_weekend_birthday_is_not_moved(self):
        result = self.book.get_upcoming_birthdays(0, today=date(2027, 1, 3))
        self.assertEqual(result[0][1].weekday(), 6)

    def test_invalid_birthday_windows(self):
        for value in (-1, 367, 1.5, True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.book.get_upcoming_birthdays(value)

    def test_no_birthday_is_skipped(self):
        self.record.birthday = None
        self.assertEqual(self.book.get_upcoming_birthdays(366), [])
