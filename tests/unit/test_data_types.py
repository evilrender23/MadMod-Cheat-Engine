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


def test_integer_overflow_is_actionable() -> None:
    with pytest.raises(ValueParseError, match="desborda"):
        parse_value(DataType.INT8, "128")


def test_float_literals() -> None:
    assert math.isnan(float(parse_value(DataType.FLOAT64, "nan")))
    assert parse_value(DataType.FLOAT32, "inf") == math.inf


def test_aob_wildcard_and_invalid_pattern() -> None:
    assert parse_aob("DE ?? BE") == (b"\xde\x00\xbe", b"\xff\x00\xff")
    assert parse_aob("DE??BE") == (b"\xde\x00\xbe", b"\xff\x00\xff")
    with pytest.raises(PatternError):
        parse_aob("DE A? BE")


def test_address_format() -> None:
    assert format_hex(0x7FF6B0C20000) == "0x00007FF6B0C20000"
