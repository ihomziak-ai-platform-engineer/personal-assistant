# Personal Assistant

A command-line application for managing contacts, birthdays and notes.
Contacts and notes are saved locally after each change and restored on startup.

The application requires **Python 3.10 or later** and has no runtime
dependencies outside the standard library. Commands use English names;
prompts and error messages are in Ukrainian.

## Features

- Contacts with names, multiple phone numbers, addresses, email and birthdays.
- Contact search, editing, renaming and deletion.
- Birthday reminders for a date range or an exact number of days ahead.
- Text notes with titles, permanent IDs and tags.
- Note search by text or tag, with alphabetical tag groups.
- Input validation and automatic local storage.

## Installation

Clone the repository, or extract the ZIP and open its root directory:

```bash
git clone https://github.com/ihomziak-ai-platform-engineer/personal-assistant.git
cd personal-assistant
```

### macOS and Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
personal-assistant
```

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .
personal-assistant
```

If PowerShell does not allow activation, run the environment's executables
without activating it:

```powershell
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\personal-assistant.exe
```

Once installed, `personal-assistant` can be run from any directory while the
virtual environment is active. Activate the environment again in a new terminal.
You can also run the application as a module:

```bash
python -m personal_assistant
```

If you use `pipx`, install the CLI with `pipx install .` instead.

## Quick start

Enter these commands at the `assistant>` prompt:

```text
add "Alice Brown" 0501234567 --email alice@example.com --address "10 Green Street" --birthday 15.04.1990
add "Alice Brown" 0671234567
show "Alice Brown"
find "Green Street" address
birthdays 30
note-add "Python" "Review classes and decorators" python study
tag-add 1 practice
note-find "decorators"
tag-find python
notes-sort
exit
```

The example assumes an empty notebook. Otherwise, use the ID returned by
`note-add` in place of `1`.

Put values containing spaces in **double quotes**. Apostrophes are supported,
for example `add "Alex O'Connor" 0501234567`. Use `\"` for a double quote
inside a quoted value. Each note is entered on one line.

## Contact commands

Arguments in square brackets are optional. Do not type the brackets.

| Command | Description |
| --- | --- |
| `add "NAME" [PHONE] [--email EMAIL] [--address "ADDRESS"] [--birthday DD.MM.YYYY]` | Create a contact with optional details |
| `add "NAME" PHONE` | Add another phone number to an existing contact |
| `show "NAME"` | Show all details for a contact |
| `all` | List contacts by name |
| `phone "NAME"` | Show a contact's phone numbers |
| `find "QUERY" [FIELD]` | Search contacts by a case-insensitive substring |
| `change "NAME" OLD_PHONE NEW_PHONE` | Replace a phone number |
| `remove-phone "NAME" PHONE` | Remove a phone number |
| `rename "OLD_NAME" "NEW_NAME"` | Rename a contact |
| `set-email "NAME" EMAIL` | Set or replace the email address |
| `set-address "NAME" "ADDRESS"` | Set or replace the address |
| `set-birthday "NAME" DD.MM.YYYY` | Set or replace the birthday |
| `add-birthday "NAME" DD.MM.YYYY` | Alias for `set-birthday` |
| `show-birthday "NAME"` | Show the birthday |
| `clear-field "NAME" FIELD` | Clear `email`, `address` or `birthday` |
| `delete "NAME"` | Delete a contact |
| `birthdays [N]` | List birthdays from today through N days ahead |
| `birthdays N exact` | List birthdays exactly N days ahead |

Search fields: `all` (default), `name`, `phone`, `email`, `address` and
`birthday`. For example: `find "@example.com" email`.

For an existing contact, `add` accepts only an additional phone number. Use
`set-email`, `set-address` or `set-birthday` to change other fields. When
creating a contact, options may appear in any order after the name and
optional phone number.

### Birthday rules

- N must be an integer from 0 to 366; the default is 7.
- The range includes today and the final day. Use `birthdays 0` for today.
- Each contact appears once in a range, using their next birthday.
- `exact` checks the target date, including dates in the following year.
- February 29 is treated as February 28 in non-leap years.
- Weekend birthdays keep their calendar date.
- Today's date comes from the operating system's local calendar.

## Note and tag commands

| Command | Description |
| --- | --- |
| `note-add "TITLE" "TEXT" [tags...]` | Create a note and return its ID |
| `notes` | List notes by ID |
| `note-show ID` | Show a note |
| `note-find "QUERY"` | Search titles and text, ignoring case |
| `note-edit ID "TITLE" "TEXT"` | Replace the title and text, keeping the tags |
| `note-delete ID` | Delete a note |
| `tag-add ID TAG [more_tags...]` | Add tags without duplicates |
| `tag-remove ID TAG` | Remove a tag |
| `tag-find TAG` | Find notes with an exact tag |
| `notes-sort` | Group notes by tags in alphabetical order |

Tags are case-insensitive: `Python`, `python` and `#PYTHON` refer to the same
tag. A note with multiple tags appears in each matching group. Notes without
tags appear in the last group. Notes within each group are ordered by ID.
Deleted IDs are not reused, including after a restart.

## General commands

| Command | Description |
| --- | --- |
| `hello` | Display a greeting |
| `help` | List commands |
| `help add` | Show the syntax of a contact or note command |
| `exit` or `close` | Exit the application |

`Ctrl+C` or end-of-input also exits. Completed commands have already been
saved. Deletions take effect immediately; there is no undo command.

Command-line options:

```bash
personal-assistant --help
personal-assistant --version
personal-assistant --data-dir ./demo-data
```

## Validation

| Field | Accepted values |
| --- | --- |
| Name | 1–100 characters; extra spaces are normalized; unique ignoring case |
| Phone | Exactly 10 ASCII digits; no duplicates within a contact |
| Email | ASCII email syntax such as `name@example.com`, up to 254 characters |
| Address | 1–300 characters |
| Birthday | A valid date in `DD.MM.YYYY` format, no later than today |
| Note title | 1–120 characters |
| Note text | 1–10,000 characters on one line |
| Tag | 1–50 letters, digits, underscores or hyphens; an optional leading `#` |
| Note ID | A positive integer identifying an existing note |

Text fields reject control characters and trim surrounding whitespace.
Phone numbers must be entered without spaces, hyphens or a country-code
prefix. Email validation checks syntax, not whether a mailbox exists;
Unicode and quoted local parts are not supported. Postal addresses are
stored as text without checking their physical existence.

## Data storage

Data is stored in `~/.personal_assistant/data.pkl`. On Windows, `~` refers to
the user's home directory. The absolute path is displayed on startup and
does not depend on the directory from which the application is launched.
Use `--data-dir` to select another location.

Each change is written to a temporary file before it replaces the saved
file. The in-memory state is updated after the write succeeds. If saving
fails, the command reports an error and leaves the session's previous state
intact. The data file is limited to 10 MiB.

Only one session can use a data directory at a time. The operating system
releases the lock when the process exits. A leftover `data.lock` file is
normal and does not mean the directory is still locked.

If a data file is damaged or incompatible, startup stops without overwriting
it. To make a backup, close the application and copy `data.pkl`; restore a
backup while the application is closed.

Storage uses a versioned pickle dictionary. Class and function imports are
blocked during loading, and stored fields are validated. Only use data
files created by this application; do not load untrusted pickle files.

## Project structure

| Module | Responsibility |
| --- | --- |
| `src/personal_assistant/fields.py` | Field types and validation |
| `src/personal_assistant/contacts.py` | Contacts, search and birthday calculations |
| `src/personal_assistant/notes.py` | Notes, IDs and tags |
| `src/personal_assistant/storage.py` | Serialization, file writes and locking |
| `src/personal_assistant/commands.py` | Command handlers and argument validation |
| `src/personal_assistant/cli.py` | Input parsing, the interactive loop and session state |
| `tests/` | Tests for models, commands and storage |

Field types inherit from `Field`; contact and note books extend `UserDict`.
A contact contains its validated fields, and `AssistantData` contains both
books. Domain models are independent of file storage and the CLI.

## Development

Install the package in editable mode with the style checker:

```bash
python -m pip install -e ".[dev]"
```

Run tests and check formatting from the repository root:

```bash
python -m unittest discover -s tests -v
python -m pycodestyle src tests
```

GitHub Actions runs these checks on Linux with Python 3.10, 3.12 and 3.13,
and on macOS and Windows with Python 3.12. It also checks that the installed
command runs from outside the project directory.
