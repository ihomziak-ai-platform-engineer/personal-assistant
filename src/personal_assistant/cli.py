"""Interactive CLI and the save-before-commit application boundary."""

import argparse
import shlex
import sys
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from difflib import get_close_matches
from functools import wraps
from pathlib import Path
from typing import Protocol

from personal_assistant import __version__
from personal_assistant.commands import build_commands, require_args
from personal_assistant.storage import (
    AssistantData,
    PickleStorage,
    StorageError,
)


class Repository(Protocol):
    """The application depends on a small persistence contract."""

    def save(self, data: AssistantData) -> None:
        ...


@dataclass(frozen=True)
class Response:
    message: str
    should_exit: bool = False


def parse_input(user_input: str) -> tuple[str, list[str]]:
    """Parse quoted values while keeping Ukrainian apostrophes literal.

    Commands are never passed to a shell. Double quotes group a value with
    spaces; # is a tag character, not the start of a comment.
    """
    lexer = shlex.shlex(user_input, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    lexer.quotes = '"'
    try:
        parts = list(lexer)
    except ValueError as exc:
        raise ValueError('Перевірте парність подвійних лапок "...".') from exc
    return (parts[0].casefold(), parts[1:]) if parts else ("", [])


def input_error(func: Callable) -> Callable:
    """Convert expected input/storage failures to a response, not an exit."""
    @wraps(func)
    def wrapper(*args, **kwargs) -> Response:
        try:
            return func(*args, **kwargs)
        except (ValueError, StorageError) as exc:
            return Response(f"Помилка: {exc}")

    return wrapper


class Session:
    """Own state and persist each mutation before reporting success."""

    def __init__(self, data: AssistantData, repository: Repository) -> None:
        self.data = data
        self.repository = repository
        self.commands = build_commands()

    @input_error
    def execute(self, user_input: str) -> Response:
        command, args = parse_input(user_input)
        if not command:
            return Response("")
        if command in {"exit", "close"}:
            require_args(args, 0, command)
            return Response("До побачення!", should_exit=True)
        if command == "hello":
            require_args(args, 0, "hello")
            return Response(
                "Чим можу допомогти? Введіть help для списку команд."
            )
        if command == "help":
            if len(args) > 1:
                raise ValueError("Використання: help [команда]")
            if args:
                spec = self.commands.get(args[0].casefold())
                if spec is None:
                    raise ValueError("Невідома команда для довідки.")
                return Response(spec.usage)
            usages = [spec.usage for spec in self.commands.values()]
            return Response(
                "Команди (значення з пробілами беріть у подвійні лапки):\n"
                + "\n".join(dict.fromkeys(usages))
                + "\nadd-birthday — псевдонім set-birthday"
                + "\nhello | help [команда] | exit | close"
            )
        spec = self.commands.get(command)
        if spec is None:
            matches = get_close_matches(command, self.commands, n=1)
            hint = (
                f" Можливо, ви мали на увазі {matches[0]}?" if matches else ""
            )
            raise ValueError(f"Невідома команда. Введіть help.{hint}")
        if spec.mutates:
            candidate = deepcopy(self.data)
            message = spec.handler(args, candidate)
            self.repository.save(candidate)
            self.data = candidate
        else:
            message = spec.handler(args, self.data)
        return Response(message)


def run_loop(session: Session) -> None:
    """EOF and Ctrl+C leave the last successfully saved state intact."""
    print("Персональний помічник. Введіть help для списку команд.")
    while True:
        try:
            response = session.execute(input("assistant> "))
        except (EOFError, KeyboardInterrupt):
            print("\nДо побачення!")
            return
        if response.message:
            print(response.message)
        if response.should_exit:
            return


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Персональний помічник: контакти, дні народження, нотатки."
    )
    parser.add_argument(
        "--data-dir", type=Path, default=None,
        help="Інша папка даних (типово ~/.personal_assistant).",
    )
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        with PickleStorage(args.data_dir) as repository:
            session = Session(repository.load(), repository)
            print(f"Файл даних: {repository.path}")
            run_loop(session)
    except StorageError as exc:
        print(f"Помилка сховища: {exc}", file=sys.stderr)
        return 1
    return 0
