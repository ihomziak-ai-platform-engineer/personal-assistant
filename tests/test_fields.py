"""Boundary cases for values entered by users or loaded from disk."""

import unittest
from datetime import date, timedelta

from personal_assistant.fields import (
    Address,
    Birthday,
    Email,
    Name,
    Phone,
    Tag,
)


class FieldTests(unittest.TestCase):
    def test_name_normalizes_whitespace(self):
        self.assertEqual(Name("  Іван   Петренко  ").value, "Іван Петренко")

    def test_invalid_text_is_rejected(self):
        for value in ("", "   ", "\x1b[31mtext", "name\nnext", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Name(value)

    def test_phone_preserves_leading_zero(self):
        self.assertEqual(Phone("0501234567").value, "0501234567")

    def test_phone_rejects_wrong_formats_and_unicode_digits(self):
        for value in (
            "050123456", "05012345678", "+380501234567", "050 123456",
            "٠٥٠١٢٣٤٥٦٧", "050abcdefg", 501234567,
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Phone(value)

    def test_email_preserves_local_case_and_normalizes_domain(self):
        self.assertEqual(
            Email("User+tag@EXAMPLE.COM").value, "User+tag@example.com"
        )

    def test_email_rejects_invalid_local_and_domain(self):
        for value in (
            "test", "@example.com", "a@@example.com", "a@localhost",
            ".a@example.com", "a.@example.com", "a..b@example.com",
            "a@-example.com", "a@example-.com", "a@ex ample.com",
            "a@example..com", "a\nb@example.com", "a@" + "x" * 64 + ".com",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Email(value)

    def test_valid_leap_birthday(self):
        self.assertEqual(Birthday("29.02.2000").value, date(2000, 2, 29))

    def test_small_year_roundtrip(self):
        self.assertEqual(str(Birthday("01.01.0001")), "01.01.0001")

    def test_invalid_dates(self):
        future = (date.today() + timedelta(days=1)).strftime("%d.%m.%Y")
        for value in ("29.02.2001", "31.04.2000", "1.01.2000", future):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Birthday(value)

    def test_address_validation(self):
        self.assertEqual(Address("  Київ, вул. Миру 1  ").value,
                         "Київ, вул. Миру 1")
        with self.assertRaises(ValueError):
            Address("x" * 301)

    def test_tags(self):
        self.assertEqual(Tag("#Навчання").value, "навчання")
        for value in ("#", "two words", "a,b", "##python", "x" * 51):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Tag(value)

    def test_field_value_is_read_only(self):
        phone = Phone("0501234567")
        with self.assertRaises(AttributeError):
            phone.value = "bad"
