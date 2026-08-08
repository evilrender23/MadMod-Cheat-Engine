"""Tests for value parsing and encoding contracts."""

import math

import pytest

from mempilot.core.data_types import (
    DataType,
    decode_value,
    encode_value,
    format_hex,
    parse_aob,
    parse_value,
)
from mempilot.core.exceptions import PatternError, ValueParseError


@pytest.mark.parametrize(
    ("data_type", "text", "decoded"),
    [
        (DataType.INT8, "-12", "-12"),
        (DataType.INT16, "7FFFh", "32767"),
        (DataType.INT32, "0x123456", "1193046"),
        (DataType.INT64, "-100000", "-100000"),
        (DataType.UINT8, "255", "255"),
        (DataType.UINT16, "65535", "65535"),
        (DataType.UINT32, "0xFFFFFFFF", "4294967295"),
        (DataType.UINT64, "123", "123"),
        (DataType.FLOAT32, "1,25", "1.25"),
        (DataType.FLOAT64, "-3.5", "-3.5"),
        (DataType.BOOL, "sí", "true"),
        (DataType.STRING_UTF8, "Piloto", "Piloto"),
        (DataType.STRING_UTF16, "Memoria", "Memoria"),
    ],
)
def test_round_trip(data_type: DataType, text: str, decoded: str) -> None:
    assert decode_value(data_type, encode_value(data_type, text)) == decoded


@pytest.mark.parametrize(
    ("data_type", "too_low", "too_high"),
    [
        (DataType.INT8, "-129", "128"),
        (DataType.INT16, "-32769", "32768"),
        (DataType.INT32, "-2147483649", "2147483648"),
        (DataType.INT64, "-9223372036854775809", "9223372036854775808"),
        (DataType.UINT8, "-1", "256"),
        (DataType.UINT16, "-1", "65536"),
        (DataType.UINT32, "-1", "4294967296"),
        (DataType.UINT64, "-1", "18446744073709551616"),
    ],
)
def test_integer_overflow_is_actionable(data_type: DataType, too_low: str, too_high: str) -> None:
    for text in (too_low, too_high):
        with pytest.raises(ValueParseError, match="desborda"):
            parse_value(data_type, text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("42", 42),
        ("0x2A", 42),
        ("0X2a", 42),
        ("2Ah", 42),
        ("2aH", 42),
    ],
)
def test_integer_formats(text: str, expected: int) -> None:
    assert parse_value(DataType.INT32, text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("true", True),
        ("1", True),
        ("sí", True),
        ("si", True),
        ("verdadero", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("falso", False),
    ],
)
def test_boolean_vocabulary(text: str, expected: bool) -> None:
    assert parse_value(DataType.BOOL, text) is expected


def test_float_literals() -> None:
    assert math.isnan(float(parse_value(DataType.FLOAT64, "nan")))
    assert parse_value(DataType.FLOAT32, "inf") == math.inf


def test_aob_wildcard_and_invalid_pattern() -> None:
    assert parse_aob("DE ?? BE") == (b"\xde\x00\xbe", b"\xff\x00\xff")
    assert parse_aob("DE??BE") == (b"\xde\x00\xbe", b"\xff\x00\xff")
    assert parse_aob("DE ? BE") == (b"\xde\x00\xbe", b"\xff\x00\xff")
    for invalid in ("", "DE A? BE", "DEA"):
        with pytest.raises(PatternError):
            parse_aob(invalid)


def test_address_format() -> None:
    assert format_hex(0x7FF6B0C20000) == "0x00007FF6B0C20000"
