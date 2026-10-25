"""Allow ``python -m personal_assistant`` after installation."""

from personal_assistant.cli import main

raise SystemExit(main())
