"""Data type parsing, encoding, and formatting."""

from enum import StrEnum
from typing import Any, cast

import numpy as np

from mempilot.core.exceptions import PatternError, ValueParseError


class DataType(StrEnum):
    INT8 = "int8"
    INT16 = "int16"
    INT32 = "int32"
    INT64 = "int64"
    UINT8 = "uint8"
    UINT16 = "uint16"
    UINT32 = "uint32"
    UINT64 = "uint64"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    BOOL = "bool"
    STRING_UTF8 = "string_utf8"
    STRING_UTF16 = "string_utf16"
    AOB = "aob"
    BYTES = "bytes"


NUMERIC_TYPES: frozenset[DataType] = frozenset(
    {
        DataType.INT8,
        DataType.INT16,
        DataType.INT32,
        DataType.INT64,
        DataType.UINT8,
        DataType.UINT16,
        DataType.UINT32,
        DataType.UINT64,
        DataType.FLOAT32,
        DataType.FLOAT64,
        DataType.BOOL,
    }
)
FLOAT_TYPES: frozenset[DataType] = frozenset({DataType.FLOAT32, DataType.FLOAT64})
VARIABLE_TYPES: frozenset[DataType] = frozenset(
    {DataType.STRING_UTF8, DataType.STRING_UTF16, DataType.AOB, DataType.BYTES}
)

_DTYPE_NAMES: dict[DataType, str] = {
    DataType.INT8: "i1",
    DataType.INT16: "<i2",
    DataType.INT32: "<i4",
    DataType.INT64: "<i8",
    DataType.UINT8: "u1",
    DataType.UINT16: "<u2",
    DataType.UINT32: "<u4",
    DataType.UINT64: "<u8",
    DataType.FLOAT32: "<f4",
    DataType.FLOAT64: "<f8",
    DataType.BOOL: "?",
}
_INTEGER_BITS: dict[DataType, tuple[int, bool]] = {
    DataType.INT8: (8, True),
    DataType.INT16: (16, True),
    DataType.INT32: (32, True),
    DataType.INT64: (64, True),
    DataType.UINT8: (8, False),
    DataType.UINT16: (16, False),
    DataType.UINT32: (32, False),
    DataType.UINT64: (64, False),
}
_TRUE_VALUES = frozenset({"true", "1", "sí", "si", "verdadero"})
_FALSE_VALUES = frozenset({"false", "0", "no", "falso"})


def numpy_dtype(dt: DataType) -> np.dtype[Any]:
    """Return the little-endian NumPy dtype for a fixed-width type."""
    try:
        return np.dtype(_DTYPE_NAMES[dt])
    except KeyError as exc:
        raise ValueError(f"{dt.value} no tiene tamaño fijo") from exc


def type_size(dt: DataType) -> int:
    """Return the encoded size of a fixed-width value."""
    if dt in VARIABLE_TYPES:
        raise ValueError(f"{dt.value} no tiene tamaño fijo")
    return int(numpy_dtype(dt).itemsize)


def _parse_integer(text: str) -> int:
    value = text.strip()
    if not value:
        raise ValueError
    sign = ""
    if value[0] in "+-":
        sign, value = value[0], value[1:]
    if value.lower().startswith("0x"):
        digits = value[2:]
        base = 16
    elif value.lower().endswith("h"):
        digits = value[:-1]
        base = 16
    else:
        digits = value
        base = 10
    if not digits:
        raise ValueError
    return int(sign + digits, base)


def parse_value(dt: DataType, text: str) -> int | float | bool | bytes:
    """Parse user text according to a data type and validate its range."""
    try:
        if dt in _INTEGER_BITS:
            parsed = _parse_integer(text)
            bits, signed = _INTEGER_BITS[dt]
            low = -(1 << (bits - 1)) if signed else 0
            high = (1 << (bits - (1 if signed else 0))) - 1
            if not low <= parsed <= high:
                raise ValueParseError(
                    f"El valor {text!r} desborda el rango de {dt.value} ({low} a {high})."
                )
            return parsed
        if dt in FLOAT_TYPES:
            return float(text.strip().replace(",", "."))
        if dt is DataType.BOOL:
            normalized = text.strip().casefold()
            if normalized in _TRUE_VALUES:
                return True
            if normalized in _FALSE_VALUES:
                return False
            raise ValueError
        if dt is DataType.STRING_UTF8:
            return text.encode("utf-8")
        if dt is DataType.STRING_UTF16:
            return text.encode("utf-16-le")
        if dt is DataType.AOB:
            return parse_aob(text)[0]
        if dt is DataType.BYTES:
            compact = "".join(text.split())
            if len(compact) % 2:
                raise ValueError
            return bytes.fromhex(compact)
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, ValueParseError):
            raise
        raise ValueParseError(
            f"No se puede interpretar {text!r} como {dt.value}. Corrige el valor."
        ) from exc
    raise ValueParseError(f"Tipo de dato desconocido: {dt!r}.")


def encode_value(dt: DataType, text: str) -> bytes:
    """Encode user text into its in-memory representation."""
    parsed = parse_value(dt, text)
    if dt in NUMERIC_TYPES:
        return np.asarray([parsed], dtype=numpy_dtype(dt)).tobytes()
    return cast(bytes, parsed)


def decode_value(dt: DataType, raw: bytes) -> str:
    """Decode memory bytes into display text."""
    if dt in NUMERIC_TYPES:
        size = type_size(dt)
        if len(raw) < size:
            raise ValueParseError(f"Se necesitan {size} bytes para decodificar {dt.value}.")
        value = np.frombuffer(raw[:size], dtype=numpy_dtype(dt), count=1)[0]
        if dt is DataType.BOOL:
            return "true" if bool(value) else "false"
        return str(value.item())
    if dt is DataType.STRING_UTF8:
        return raw.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    if dt is DataType.STRING_UTF16:
        usable = raw[: len(raw) - len(raw) % 2]
        terminator = next(
            (
                index
                for index in range(0, len(usable), 2)
                if usable[index : index + 2] == b"\x00\x00"
            ),
            len(usable),
        )
        return usable[:terminator].decode("utf-16-le", errors="replace")
    return " ".join(f"{byte:02X}" for byte in raw)


def parse_aob(pattern: str) -> tuple[bytes, bytes]:
    """Parse an array-of-bytes pattern and its full-byte wildcard mask."""
    stripped = pattern.strip()
    if not stripped:
        raise PatternError("El patrón AOB está vacío. Escribe al menos un byte hexadecimal.")
    if any(char.isspace() for char in stripped):
        tokens = stripped.split()
    else:
        if "?" in stripped:
            if len(stripped) % 2:
                raise PatternError("Los comodines AOB deben ocupar un byte completo: ? o ??.")
            tokens = [stripped[index : index + 2] for index in range(0, len(stripped), 2)]
        else:
            if len(stripped) % 2:
                raise PatternError("El patrón hexadecimal debe contener pares de dígitos.")
            tokens = [stripped[index : index + 2] for index in range(0, len(stripped), 2)]
    values = bytearray()
    mask = bytearray()
    for token in tokens:
        if token in {"?", "??"}:
            values.append(0)
            mask.append(0)
            continue
        if len(token) != 2:
            raise PatternError(f"Token AOB inválido: {token!r}. Usa pares hexadecimales.")
        try:
            values.append(int(token, 16))
        except ValueError as exc:
            raise PatternError(f"Token AOB inválido: {token!r}. Usa 00-FF o ??.") from exc
        mask.append(0xFF)
    return bytes(values), bytes(mask)


def format_hex(address: int) -> str:
    """Format an address as a 16-digit uppercase hexadecimal value."""
    if address < 0:
        raise ValueError("Una dirección no puede ser negativa")
    return f"0x{address:016X}"
