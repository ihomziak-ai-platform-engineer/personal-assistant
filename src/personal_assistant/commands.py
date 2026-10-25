"""Small command handlers: validate arguments, then call domain methods."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import partial

from personal_assistant.contacts import Record
from personal_assistant.storage import AssistantData


@dataclass(frozen=True)
class Command:
    """Metadata used for dispatch, help and persistence decisions."""

    handler: Callable[[list[str], AssistantData], str]
    usage: str
    mutates: bool = False


def require_args(args: list[str], count: int, usage: str) -> list[str]:
    if len(args) != count:
        raise ValueError(f"Використання: {usage}")
    return args


def render_items(items: Iterable[object], empty: str) -> str:
    return "\n".join(map(str, items)) or empty


def add_contact(args: list[str], data: AssistantData) -> str:
    usage = (
        'add "Ім’я" [телефон] [--email EMAIL] '
        '[--address "Адреса"] [--birthday DD.MM.YYYY]'
    )
    if not args:
        raise ValueError(f"Використання: {usage}")
    name, *remaining = args
    phone = None
    if remaining and not remaining[0].startswith("--"):
        phone = remaining.pop(0)
    options = {}
    while remaining:
        if len(remaining) < 2:
            raise ValueError(f"Використання: {usage}")
        option, value = remaining[:2]
        if option not in {"--email", "--address", "--birthday"}:
            raise ValueError(f"Невідомий параметр: {option}.")
        if option in options:
            raise ValueError(f"Параметр {option} вказано двічі.")
        options[option] = value
        del remaining[:2]
    existing = data.contacts.find(name)
    if existing is not None:
        if options or phone is None:
            raise ValueError("Контакт існує. Використайте команди set-*.")
        existing.add_phone(phone)
        return "Номер додано до контакту."
    record = Record(name)
    if phone is not None:
        record.add_phone(phone)
    setters = {
        "--email": record.set_email,
        "--address": record.set_address,
        "--birthday": record.add_birthday,
    }
    for option, value in options.items():
        setters[option](value)
    data.contacts.add_record(record)
    return "Контакт додано."


def change_contact(args: list[str], data: AssistantData) -> str:
    name, old, new = require_args(args, 3, 'change "Ім’я" СТАРИЙ НОВИЙ')
    data.contacts.require(name).edit_phone(old, new)
    return "Номер телефону змінено."


def remove_phone(args: list[str], data: AssistantData) -> str:
    name, phone = require_args(args, 2, 'remove-phone "Ім’я" ТЕЛЕФОН')
    data.contacts.require(name).remove_phone(phone)
    return "Номер телефону видалено."


def show_contact(args: list[str], data: AssistantData) -> str:
    (name,) = require_args(args, 1, 'show "Ім’я"')
    return str(data.contacts.require(name))


def show_phone(args: list[str], data: AssistantData) -> str:
    (name,) = require_args(args, 1, 'phone "Ім’я"')
    record = data.contacts.require(name)
    phones = "; ".join(map(str, record.phones)) or "немає телефонів"
    return f"{record.name}: {phones}"


def show_all(args: list[str], data: AssistantData) -> str:
    require_args(args, 0, "all")
    records = sorted(
        data.contacts.values(), key=lambda record: record.name.value.casefold()
    )
    return render_items(records, "Адресна книга порожня.")


def find_contacts(args: list[str], data: AssistantData) -> str:
    if len(args) not in (1, 2):
        raise ValueError('Використання: find "Запит" [поле]')
    query = args[0]
    field = args[1].lower() if len(args) == 2 else "all"
    return render_items(
        data.contacts.search(query, field), "Контактів не знайдено."
    )


def rename_contact(args: list[str], data: AssistantData) -> str:
    old, new = require_args(args, 2, 'rename "Старе ім’я" "Нове ім’я"')
    data.contacts.rename(old, new)
    return "Ім'я контакту змінено."


def delete_contact(args: list[str], data: AssistantData) -> str:
    (name,) = require_args(args, 1, 'delete "Ім’я"')
    data.contacts.delete(name)
    return "Контакт видалено."


def set_contact_field(
    args: list[str], data: AssistantData, *, field: str
) -> str:
    name, value = require_args(args, 2, f'set-{field} "Ім’я" "Значення"')
    record = data.contacts.require(name)
    setters = {
        "email": record.set_email,
        "address": record.set_address,
        "birthday": record.add_birthday,
    }
    setters[field](value)
    return "Поле контакту збережено."


def clear_field(args: list[str], data: AssistantData) -> str:
    name, field = require_args(args, 2, 'clear-field "Ім’я" ПОЛЕ')
    if field not in {"email", "address", "birthday"}:
        raise ValueError("Можна очистити email, address або birthday.")
    setattr(data.contacts.require(name), field, None)
    return "Поле контакту очищено."


def show_birthday(args: list[str], data: AssistantData) -> str:
    (name,) = require_args(args, 1, 'show-birthday "Ім’я"')
    record = data.contacts.require(name)
    return f"{record.name}: {record.birthday or 'день народження не вказано'}"


def birthdays(args: list[str], data: AssistantData) -> str:
    if len(args) > 2 or (len(args) == 2 and args[1] != "exact"):
        raise ValueError("Використання: birthdays [N] [exact]")
    try:
        days = int(args[0]) if args else 7
    except ValueError as exc:
        raise ValueError("Кількість днів має бути цілим числом.") from exc
    upcoming = data.contacts.get_upcoming_birthdays(
        days, exact=len(args) == 2
    )
    return "\n".join(
        f"{record.name}: {birthday:%d.%m.%Y} (через {remaining} дн.)"
        for record, birthday, remaining in upcoming
    ) or "У заданому періоді днів народження немає."


def note_id(value: str) -> int:
    try:
        result = int(value)
    except ValueError as exc:
        raise ValueError("ID нотатки має бути додатним цілим числом.") from exc
    if result < 1:
        raise ValueError("ID нотатки має бути додатним цілим числом.")
    return result


def add_note(args: list[str], data: AssistantData) -> str:
    if len(args) < 2:
        raise ValueError(
            'Використання: note-add "Заголовок" "Текст" [теги...]'
        )
    note = data.notes.add(args[0], args[1], args[2:])
    return f"Нотатку додано. ID: {note.id}."


def edit_note(args: list[str], data: AssistantData) -> str:
    number, title, text = require_args(
        args, 3, 'note-edit ID "Новий заголовок" "Новий текст"'
    )
    data.notes.require(note_id(number)).edit(title, text)
    return "Нотатку змінено; теги збережено."


def delete_note(args: list[str], data: AssistantData) -> str:
    (number,) = require_args(args, 1, "note-delete ID")
    data.notes.delete(note_id(number))
    return "Нотатку видалено."


def show_note(args: list[str], data: AssistantData) -> str:
    (number,) = require_args(args, 1, "note-show ID")
    return str(data.notes.require(note_id(number)))


def all_notes(args: list[str], data: AssistantData) -> str:
    require_args(args, 0, "notes")
    return render_items(data.notes.sorted_notes(), "Нотаток ще немає.")


def find_notes(args: list[str], data: AssistantData) -> str:
    (query,) = require_args(args, 1, 'note-find "Запит"')
    return render_items(data.notes.search(query), "Нотаток не знайдено.")


def add_tags(args: list[str], data: AssistantData) -> str:
    if len(args) < 2:
        raise ValueError("Використання: tag-add ID ТЕГ [інші теги...]")
    data.notes.require(note_id(args[0])).add_tags(args[1:])
    return "Теги додано."


def remove_tag(args: list[str], data: AssistantData) -> str:
    number, tag = require_args(args, 2, "tag-remove ID ТЕГ")
    data.notes.require(note_id(number)).remove_tag(tag)
    return "Тег видалено."


def find_tag(args: list[str], data: AssistantData) -> str:
    (tag,) = require_args(args, 1, "tag-find ТЕГ")
    return render_items(data.notes.by_tag(tag), "Нотаток із цим тегом немає.")


def sort_tags(args: list[str], data: AssistantData) -> str:
    require_args(args, 0, "notes-sort")
    groups = data.notes.grouped_by_tag()
    return "\n\n".join(
        f"{tag}:\n" + "\n".join(map(str, notes)) for tag, notes in groups
    ) or "Нотаток ще немає."


def build_commands() -> dict[str, Command]:
    """Build the command registry."""
    commands = {
        "add": Command(
            add_contact,
            'add "Ім’я" [ТЕЛЕФОН] [--email EMAIL] '
            '[--address "Адреса"] [--birthday DD.MM.YYYY]',
            True,
        ),
        "change": Command(change_contact, 'change "Ім’я" СТАРИЙ НОВИЙ', True),
        "remove-phone": Command(
            remove_phone, 'remove-phone "Ім’я" ТЕЛЕФОН', True
        ),
        "phone": Command(show_phone, 'phone "Ім’я"'),
        "show": Command(show_contact, 'show "Ім’я"'),
        "all": Command(show_all, "all — усі контакти"),
        "find": Command(find_contacts, 'find "Запит" [поле]'),
        "rename": Command(rename_contact, 'rename "Старе" "Нове"', True),
        "delete": Command(delete_contact, 'delete "Ім’я"', True),
        "clear-field": Command(clear_field, 'clear-field "Ім’я" ПОЛЕ', True),
        "show-birthday": Command(show_birthday, 'show-birthday "Ім’я"'),
        "birthdays": Command(birthdays, "birthdays [N] [exact]"),
        "note-add": Command(
            add_note, 'note-add "Заголовок" "Текст" [теги...]', True
        ),
        "note-edit": Command(
            edit_note, 'note-edit ID "Заголовок" "Текст"', True
        ),
        "note-delete": Command(delete_note, "note-delete ID", True),
        "note-show": Command(show_note, "note-show ID"),
        "notes": Command(all_notes, "notes — усі нотатки"),
        "note-find": Command(find_notes, 'note-find "Запит"'),
        "tag-add": Command(add_tags, "tag-add ID ТЕГ [інші теги...]", True),
        "tag-remove": Command(remove_tag, "tag-remove ID ТЕГ", True),
        "tag-find": Command(find_tag, "tag-find ТЕГ"),
        "notes-sort": Command(sort_tags, "notes-sort — групи за тегами"),
    }
    for field in ("email", "address", "birthday"):
        commands[f"set-{field}"] = Command(
            partial(set_contact_field, field=field),
            f'set-{field} "Ім’я" "Значення"',
            True,
        )
    commands["add-birthday"] = commands["set-birthday"]
    return commands
