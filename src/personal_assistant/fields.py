"""Validated value objects shared by contacts and notes."""

import re
from datetime import date, datetime
from typing import Generic, TypeVar

T = TypeVar("T")


def clean_text(value: str, label: str, maximum: int) -> str:
    """Reject empty input and terminal control characters."""
    if not isinstance(value, str):
        raise ValueError(f"{label}: очікується текст.")
    value = value.strip()
    if not value or len(value) > maximum:
        raise ValueError(f"{label}: потрібно від 1 до {maximum} символів.")
    if not value.isprintable():
        raise ValueError(f"{label}: керувальні символи заборонені.")
    return value


class Field(Generic[T]):
    """Base wrapper with read-only access to its value."""

    def __init__(self, value: T) -> None:
        self._value = value

    @property
    def value(self) -> T:
        return self._value

    def __str__(self) -> str:
        return str(self.value)


class Name(Field[str]):
    """A contact's display name; uniqueness is managed by AddressBook."""

    def __init__(self, value: str) -> None:
        value = clean_text(value, "Ім'я", 100)
        super().__init__(" ".join(value.split()))


class Phone(Field[str]):
    """A phone number containing exactly ten ASCII digits."""

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{10}", value):
            raise ValueError("Телефон повинен містити рівно 10 цифр.")
        super().__init__(value)


class Email(Field[str]):
    """Practical ASCII email syntax validation, without a network lookup."""

    def __init__(self, value: str) -> None:
        value = clean_text(value, "Email", 254)
        local, separator, domain = value.rpartition("@")
        local_pattern = r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+"
        labels = domain.split(".")
        valid_local = (
            bool(re.fullmatch(local_pattern, local))
            and len(local) <= 64
            and not local.startswith(".")
            and not local.endswith(".")
            and ".." not in local
        )
        valid_domain = len(labels) >= 2 and all(
            re.fullmatch(
                r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label
            )
            for label in labels
        )
        if not separator or not valid_local or not valid_domain:
            raise ValueError("Некоректний email. Приклад: name@example.com.")
        super().__init__(f"{local}@{domain.lower()}")


class Address(Field[str]):
    """A free-form postal address; physical existence is not verified."""

    def __init__(self, value: str) -> None:
        super().__init__(clean_text(value, "Адреса", 300))


class Birthday(Field[date]):
    """A real, non-future calendar date in DD.MM.YYYY format."""

    def __init__(self, value: str) -> None:
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{2}\.[0-9]{2}\.[0-9]{4}", value
        ):
            raise ValueError("Дата має бути у форматі DD.MM.YYYY.")
        try:
            birthday = datetime.strptime(value, "%d.%m.%Y").date()
        except ValueError as exc:
            raise ValueError(
                "Такої дати не існує. Формат: DD.MM.YYYY."
            ) from exc
        if birthday > date.today():
            raise ValueError("День народження не може бути в майбутньому.")
        super().__init__(birthday)

    def __str__(self) -> str:
        value = self.value
        return f"{value.day:02d}.{value.month:02d}.{value.year:04d}"


class Tag(Field[str]):
    """A case-insensitive Unicode keyword, with an optional leading #."""

    def __init__(self, value: str) -> None:
        value = clean_text(value, "Тег", 51).removeprefix("#").casefold()
        if not 1 <= len(value) <= 50 or not re.fullmatch(r"[\w-]+", value):
            raise ValueError("Тег: 1–50 літер, цифр, символів _ або -.")
        super().__init__(value)
