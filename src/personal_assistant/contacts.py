"""Contact models and queries; this module does not read or write files."""

from collections import UserDict
from datetime import date, timedelta

from personal_assistant.fields import Address, Birthday, Email, Name, Phone


class Record:
    """Contact details for one person."""

    def __init__(self, name: str) -> None:
        self.name = Name(name)
        self.phones: list[Phone] = []
        self.address: Address | None = None
        self.email: Email | None = None
        self.birthday: Birthday | None = None

    def find_phone(self, phone: str) -> Phone | None:
        return next((p for p in self.phones if p.value == phone), None)

    def add_phone(self, phone: str) -> None:
        validated = Phone(phone)
        if self.find_phone(validated.value):
            raise ValueError("Такий телефон уже є в контакті.")
        self.phones.append(validated)

    def remove_phone(self, phone: str) -> None:
        existing = self.find_phone(phone)
        if existing is None:
            raise ValueError("Телефон не знайдено.")
        self.phones.remove(existing)

    def edit_phone(self, old_phone: str, new_phone: str) -> None:
        existing = self.find_phone(old_phone)
        if existing is None:
            raise ValueError("Старий телефон не знайдено.")
        validated = Phone(new_phone)
        if new_phone != old_phone and self.find_phone(new_phone):
            raise ValueError("Такий телефон уже є в контакті.")
        self.phones[self.phones.index(existing)] = validated

    def set_address(self, address: str) -> None:
        self.address = Address(address)

    def set_email(self, email: str) -> None:
        self.email = Email(email)

    def add_birthday(self, birthday: str) -> None:
        self.birthday = Birthday(birthday)

    def __str__(self) -> str:
        phones = "; ".join(map(str, self.phones)) or "немає"
        return (
            f"Контакт: {self.name} | телефони: {phones}\n"
            f"  Адреса: {self.address or '—'} | email: {self.email or '—'}\n"
            f"  День народження: {self.birthday or '—'}"
        )


class AddressBook(UserDict[str, Record]):
    """Store names by normalized key, preventing accidental overwrites."""

    @staticmethod
    def key(name: str) -> str:
        return Name(name).value.casefold()

    def add_record(self, record: Record) -> None:
        key = self.key(record.name.value)
        if key in self.data:
            raise ValueError("Контакт із таким ім'ям уже існує.")
        self.data[key] = record

    def find(self, name: str) -> Record | None:
        return self.data.get(self.key(name))

    def require(self, name: str) -> Record:
        record = self.find(name)
        if record is None:
            raise ValueError(f"Контакт '{name}' не знайдено.")
        return record

    def delete(self, name: str) -> None:
        record = self.require(name)
        del self.data[self.key(record.name.value)]

    def rename(self, old_name: str, new_name: str) -> None:
        record = self.require(old_name)
        validated = Name(new_name)
        old_key, new_key = self.key(old_name), self.key(new_name)
        if new_key != old_key and new_key in self.data:
            raise ValueError("Контакт із новим ім'ям уже існує.")
        del self.data[old_key]
        record.name = validated
        self.data[new_key] = record

    def search(self, query: str, field: str = "all") -> list[Record]:
        """Case-insensitive substring search over one field or all fields."""
        allowed = {"all", "name", "phone", "email", "address", "birthday"}
        if field not in allowed:
            raise ValueError(
                "Поля: all, name, phone, email, address, birthday."
            )
        if not query.strip():
            raise ValueError("Пошуковий запит не може бути порожнім.")
        needle = query.strip().casefold()
        results = []
        for record in self.data.values():
            values = {
                "name": str(record.name),
                "phone": " ".join(map(str, record.phones)),
                "email": str(record.email or ""),
                "address": str(record.address or ""),
                "birthday": str(record.birthday or ""),
            }
            candidates = values.values() if field == "all" else [values[field]]
            if any(needle in value.casefold() for value in candidates):
                results.append(record)
        return sorted(results, key=lambda item: item.name.value.casefold())

    def get_upcoming_birthdays(
        self,
        days: int = 7,
        *,
        today: date | None = None,
        exact: bool = False,
    ) -> list[tuple[Record, date, int]]:
        """Return the next anniversary, including today and the Nth day.

        February 29 is observed on February 28 in non-leap years.
        Calendar birthdays are never moved to a weekday.
        """
        if type(days) is not int or not 0 <= days <= 366:
            raise ValueError(
                "Кількість днів має бути цілим числом від 0 до 366."
            )
        today = today or date.today()
        result = []
        for record in self.data.values():
            if record.birthday is None:
                continue
            born = record.birthday.value

            def anniversary(year: int) -> date:
                try:
                    return born.replace(year=year)
                except ValueError:
                    return date(year, 2, 28)

            if exact:
                upcoming = today + timedelta(days=days)
                matches = anniversary(upcoming.year) == upcoming
            else:
                upcoming = anniversary(today.year)
                if upcoming < today:
                    upcoming = anniversary(today.year + 1)
                matches = 0 <= (upcoming - today).days <= days
            remaining = (upcoming - today).days
            if matches:
                result.append((record, upcoming, remaining))
        return sorted(
            result,
            key=lambda item: (item[1], item[0].name.value.casefold()),
        )
