"""Tests for centralized user-visible strings."""

from mempilot.i18n import STRINGS, t


def test_all_strings_are_nonempty() -> None:
    assert STRINGS
    assert all(key.strip() and value.strip() for key, value in STRINGS.items())


def test_missing_key_fails_loudly() -> None:
    try:
        t("missing.key")
    except KeyError:
        pass
    else:
        raise AssertionError("Una clave ausente debe lanzar KeyError")
