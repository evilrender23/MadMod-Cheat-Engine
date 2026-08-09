"""Tests for centralized user-visible strings."""

from string import Formatter

import pytest

from mempilot.agent.prompts import system_prompt
from mempilot.core.data_types import DataType, parse_aob
from mempilot.core.exceptions import PatternError, ValueParseError
from mempilot.core.scanner import ScanMode, ScanOptions, ScanRequest
from mempilot.i18n import CATALOGS, STRINGS, Language, get_language, set_language, t


def test_all_catalogs_are_complete_and_nonempty() -> None:
    assert STRINGS
    assert all(catalog.keys() == STRINGS.keys() for catalog in CATALOGS.values())
    assert all(
        key.strip() and value.strip()
        for catalog in CATALOGS.values()
        for key, value in catalog.items()
    )


def test_english_catalog_preserves_format_fields_and_translates_visible_text() -> None:
    formatter = Formatter()
    for key, spanish in CATALOGS[Language.SPANISH].items():
        english = CATALOGS[Language.ENGLISH][key]
        spanish_fields = sorted(
            field_name
            for _literal, field_name, _format_spec, _conversion in formatter.parse(spanish)
            if field_name is not None
        )
        english_fields = sorted(
            field_name
            for _literal, field_name, _format_spec, _conversion in formatter.parse(english)
            if field_name is not None
        )
        assert english_fields == spanish_fields, key
    assert CATALOGS[Language.ENGLISH]["action.attach"] == "Select process…"
    assert CATALOGS[Language.ENGLISH]["settings.language"] == "Language"


def test_language_selection_changes_runtime_catalog_and_can_be_restored() -> None:
    previous = get_language()
    try:
        set_language(Language.ENGLISH)
        assert t("status.connected") == "Connected"
        set_language("es")
        assert t("status.connected") == "Conectado"
    finally:
        set_language(previous)


def test_domain_validation_and_agent_instructions_follow_english_selection() -> None:
    set_language(Language.ENGLISH)

    with pytest.raises(ValueParseError, match="Enter a value for this condition"):
        ScanRequest(
            DataType.INT32,
            ScanMode.EXACT,
            None,
            None,
            ScanOptions(),
        ).validate()
    with pytest.raises(PatternError, match="AOB pattern is empty"):
        parse_aob("")
    assert ValueParseError().user_message().startswith("The value does not match")
    assert system_prompt().startswith("You are the M@D-Engine assistant")
    assert system_prompt().endswith("in English.\n")


def test_missing_key_fails_loudly() -> None:
    try:
        t("missing.key")
    except KeyError:
        pass
    else:
        raise AssertionError("Una clave ausente debe lanzar KeyError")
