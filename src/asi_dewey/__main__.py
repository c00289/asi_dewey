"""Allow ``python -m asi_dewey <verb> ...``."""

from .automation.cli import main

raise SystemExit(main())
