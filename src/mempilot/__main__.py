"""Command-line entry point for MemPilot and its bundled Memory Lab."""

from __future__ import annotations

import argparse
import sys

from mempilot.app import create_app
from mempilot.i18n import t
from mempilot.lab.memory_lab_app import run_lab
from mempilot.logging_setup import setup_logging


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=t("cli.description"))
    parser.add_argument("--memory-lab", action="store_true", help=t("cli.memory_lab"))
    parser.add_argument("--no-ai", action="store_true", help=t("cli.no_ai"))
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
        help=t("cli.log_level"),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse supported modes, initialize logging, and run the selected Qt app."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    options = _parser().parse_args(arguments)
    setup_logging(options.log_level)
    if options.memory_lab:
        return run_lab([])
    app, window = create_app([sys.argv[0]], no_ai=options.no_ai)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
