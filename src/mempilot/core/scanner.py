"""NumPy-based memory scanning and refinement engine."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import numpy as np
from numpy.typing import NDArray

from mempilot.core.backend import MemoryBackend, MemoryRegion
from mempilot.core.data_types import (
    FLOAT_TYPES,
    NUMERIC_TYPES,
    DataType,
    encode_value,
    numpy_dtype,
    parse_aob,
    parse_value,
    type_size,
)
from mempilot.core.exceptions import ScanCancelled, ScanError, ValueParseError

_MEM_PRIVATE = 0x20000
_MEM_MAPPED = 0x40000
_MEM_IMAGE = 0x1000000


class ScanMode(StrEnum):
    EXACT = "exact"
    UNKNOWN_INITIAL = "unknown_initial"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    INCREASED = "increased"
    DECREASED = "decreased"
    INCREASED_BY = "increased_by"
    DECREASED_BY = "decreased_by"
    BETWEEN = "between"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    AOB = "aob"
    TEXT = "text"


_RELATIVE_MODES = frozenset(
    {
        ScanMode.CHANGED,
        ScanMode.UNCHANGED,
        ScanMode.INCREASED,
        ScanMode.DECREASED,
        ScanMode.INCREASED_BY,
        ScanMode.DECREASED_BY,
    }
)
_VALUELESS_MODES = frozenset(
    {
        ScanMode.UNKNOWN_INITIAL,
        ScanMode.CHANGED,
        ScanMode.UNCHANGED,
        ScanMode.INCREASED,
        ScanMode.DECREASED,
    }
)


@dataclass(frozen=True, slots=True)
class ScanOptions:
    alignment: int = 0
    writable_only: bool = True
    include_image: bool = True
    include_mapped: bool = False
    use_tolerance: bool = True
    float_tolerance: float = 0.001
    case_sensitive: bool = True
    chunk_size: int = 4 << 20
    max_candidates: int = 10_000_000
    unknown_budget_mb: int = 512
    address_min: int = 0
    address_max: int = 0x7FFF_FFFE_FFFF


@dataclass(frozen=True, slots=True)
class ScanRequest:
    data_type: DataType
    mode: ScanMode
    value: str | None
    value2: str | None
    options: ScanOptions

    def validate(self) -> None:
        """Validate a scan request before touching process memory."""
        opts = self.options
        if opts.alignment < 0:
            raise ValueParseError("La alineación no puede ser negativa. Usa Automática o 1 byte.")
        if opts.chunk_size <= 0:
            raise ValueParseError("El tamaño de bloque debe ser mayor que cero.")
        if opts.max_candidates <= 0:
            raise ValueParseError("El límite de candidatos debe ser mayor que cero.")
        if opts.unknown_budget_mb < 0:
            raise ValueParseError("El presupuesto de memoria no puede ser negativo.")
        if opts.address_min < 0 or opts.address_max < opts.address_min:
            raise ValueParseError("El rango de direcciones no es válido. Corrige sus límites.")
        if opts.float_tolerance < 0:
            raise ValueParseError("La tolerancia no puede ser negativa.")
        if self.data_type is DataType.BYTES:
            raise ValueParseError("Bytes es un formato de visualización y no se puede escanear.")
        if self.mode is ScanMode.AOB and self.data_type is not DataType.AOB:
            raise ValueParseError("La condición AOB requiere el tipo de dato AOB.")
        if self.data_type is DataType.AOB and self.mode is not ScanMode.AOB:
            raise ValueParseError("El tipo AOB solo admite la condición AOB.")
        if self.mode is ScanMode.TEXT and self.data_type not in {
            DataType.STRING_UTF8,
            DataType.STRING_UTF16,
        }:
            raise ValueParseError("La condición Texto requiere un tipo de texto UTF-8 o UTF-16.")
        if (
            self.data_type in {DataType.STRING_UTF8, DataType.STRING_UTF16}
            and self.mode is not ScanMode.TEXT
        ):
            raise ValueParseError("Los tipos de texto solo admiten la condición Texto.")
        if (
            self.mode in _RELATIVE_MODES | {ScanMode.UNKNOWN_INITIAL}
            and self.data_type not in NUMERIC_TYPES
        ):
            raise ValueParseError("Esta condición requiere un tipo numérico.")
        if self.mode in _VALUELESS_MODES:
            if self.value is not None:
                raise ValueParseError("Esta condición no admite un valor de búsqueda.")
        elif self.value is None:
            raise ValueParseError("Esta condición requiere un valor de búsqueda.")
        if self.mode is ScanMode.BETWEEN:
            if self.value2 is None:
                raise ValueParseError("Entre requiere un límite superior en Valor 2.")
        elif self.value2 is not None:
            raise ValueParseError("Valor 2 solo se usa con la condición Entre.")
        if self.mode in {
            ScanMode.AOB,
            ScanMode.TEXT,
            ScanMode.EXACT,
            ScanMode.BETWEEN,
            ScanMode.GREATER_THAN,
            ScanMode.LESS_THAN,
            ScanMode.INCREASED_BY,
            ScanMode.DECREASED_BY,
        }:
            assert self.value is not None
            if self.mode is ScanMode.AOB:
                parse_aob(self.value)
            else:
                parse_value(self.data_type, self.value)
        if self.value2 is not None:
            assert self.value is not None
            low = parse_value(self.data_type, self.value)
            high = parse_value(self.data_type, self.value2)
            assert isinstance(low, (int, float)) and isinstance(high, (int, float))
            if low > high:
                raise ValueParseError("El límite inferior de Entre no puede superar al superior.")


@dataclass(slots=True)
class ScanProgress:
    regions_done: int
    regions_total: int
    bytes_done: int
    bytes_total: int
    candidates: int
    elapsed_s: float
    bytes_per_s: float


@dataclass(slots=True)
class CandidateSet:
    addresses: NDArray[np.uint64]
    values: NDArray[Any] | list[bytes]
    data_type: DataType

    def __len__(self) -> int:
        return int(self.addresses.size)


@dataclass(slots=True)
class UnknownSnapshot:
    chunks: list[tuple[int, bytes]]
    bytes_captured: int
    regions_skipped: int


def kernel_exact(buf: NDArray[Any], needle: Any, tol: float | None) -> NDArray[np.int64]:
    """Return indices exactly equal to a needle, optionally within a float tolerance."""
    is_float = np.issubdtype(buf.dtype, np.floating)
    if is_float and tol is None:
        unsigned = np.dtype(f"u{buf.dtype.itemsize}")
        encoded_needle = np.asarray([needle], dtype=buf.dtype).view(unsigned)[0]
        matches = buf.view(unsigned) == encoded_needle
    else:
        matches = buf == needle
        if tol is not None:
            with np.errstate(invalid="ignore"):
                matches |= np.abs(buf - needle) <= tol
    if is_float:
        matches &= ~np.isnan(buf)
    return np.flatnonzero(matches).astype(np.int64, copy=False)


def kernel_range(buf: NDArray[Any], low: Any, high: Any) -> NDArray[np.int64]:
    """Return indices within an inclusive range."""
    return np.flatnonzero((buf >= low) & (buf <= high)).astype(np.int64, copy=False)


def _equal_values(cur: NDArray[Any], prev: NDArray[Any], tol: float | None) -> NDArray[np.bool_]:
    is_float = np.issubdtype(cur.dtype, np.floating)
    if is_float and tol is None:
        unsigned = np.dtype(f"u{cur.dtype.itemsize}")
        equal = cur.view(unsigned) == prev.view(unsigned)
    else:
        equal = cur == prev
        if tol is not None:
            with np.errstate(invalid="ignore"):
                equal |= np.abs(cur - prev) <= tol
    if is_float:
        equal |= np.isnan(cur) & np.isnan(prev)
    return np.asarray(equal, dtype=np.bool_)


def kernel_compare(
    cur: NDArray[Any],
    prev: NDArray[Any],
    mode: ScanMode,
    delta: Any | None,
    tol: float | None,
) -> NDArray[np.bool_]:
    """Compare current and previous numeric values for a refinement mode."""
    if cur.shape != prev.shape:
        raise ValueError("Los vectores actual y anterior deben tener la misma forma")
    equal = _equal_values(cur, prev, tol)
    if mode is ScanMode.CHANGED:
        return ~equal
    if mode is ScanMode.UNCHANGED:
        return equal
    if mode is ScanMode.INCREASED:
        return np.asarray(cur > prev, dtype=np.bool_)
    if mode is ScanMode.DECREASED:
        return np.asarray(cur < prev, dtype=np.bool_)
    if delta is None:
        raise ValueError("Esta comparación requiere un delta")
    if mode is ScanMode.INCREASED_BY:
        target = prev + delta
    elif mode is ScanMode.DECREASED_BY:
        target = prev - delta
    else:
        raise ValueError(f"Modo de comparación no compatible: {mode.value}")
    return _equal_values(cur, np.asarray(target, dtype=cur.dtype), tol)


def kernel_aob(buf: NDArray[np.uint8], pattern: bytes, mask: bytes) -> NDArray[np.int64]:
    """Return start offsets matching a byte pattern with full-byte wildcards."""
    if not pattern or len(pattern) != len(mask):
        raise ValueError("El patrón y la máscara deben tener la misma longitud no nula")
    if buf.size < len(pattern):
        return np.empty(0, dtype=np.int64)
    windows = np.lib.stride_tricks.sliding_window_view(buf, len(pattern))
    expected = np.frombuffer(pattern, dtype=np.uint8)
    selected = np.frombuffer(mask, dtype=np.uint8).astype(np.bool_)
    if not np.any(selected):
        return np.arange(windows.shape[0], dtype=np.int64)
    return np.flatnonzero(np.all(windows[:, selected] == expected[selected], axis=1)).astype(
        np.int64, copy=False
    )


class _ProgressReporter:
    def __init__(self, callback: Callable[[ScanProgress], None], total: int, regions: int) -> None:
        self._callback = callback
        self._total = total
        self._regions = regions
        self._started = time.monotonic()
        self._last = self._started - 0.1

    def emit(self, regions_done: int, bytes_done: int, candidates: int) -> None:
        now = time.monotonic()
        if now - self._last < 0.1:
            return
        elapsed = max(now - self._started, 1e-9)
        self._callback(
            ScanProgress(
                regions_done=regions_done,
                regions_total=self._regions,
                bytes_done=bytes_done,
                bytes_total=self._total,
                candidates=candidates,
                elapsed_s=elapsed,
                bytes_per_s=bytes_done / elapsed,
            )
        )
        self._last = now


def _tolerance(req: ScanRequest) -> float | None:
    if req.data_type in FLOAT_TYPES and req.options.use_tolerance:
        return req.options.float_tolerance
    return None


def _numeric_slices(
    raw: bytes,
    base: int,
    data_type: DataType,
    alignment: int,
    primary_size: int,
) -> Iterator[tuple[NDArray[np.int64], NDArray[Any]]]:
    dtype = numpy_dtype(data_type)
    size = int(dtype.itemsize)
    effective_alignment = size if alignment == 0 else alignment
    starts: Iterable[int]
    if effective_alignment == 1:
        starts = range(size)
    elif effective_alignment == size:
        starts = ((-base) % size,)
    else:
        first = (-base) % effective_alignment
        max_start = len(raw) - size
        if first > max_start:
            return
        offsets = np.arange(first, max_start + 1, effective_alignment, dtype=np.int64)
        values = np.ndarray(
            shape=(offsets.size,),
            dtype=dtype,
            buffer=raw,
            offset=first,
            strides=(effective_alignment,),
        )
        primary = offsets < primary_size
        if np.any(primary):
            yield offsets[primary], values[primary]
        return
    for offset in starts:
        count = (len(raw) - offset) // size
        if count <= 0:
            continue
        values = np.frombuffer(raw, dtype=dtype, count=count, offset=offset)
        offsets = offset + np.arange(count, dtype=np.int64) * size
        primary = offsets < primary_size
        if np.any(primary):
            yield offsets[primary], values[primary]


def _empty_candidates(data_type: DataType) -> CandidateSet:
    values: NDArray[Any] | list[bytes] = (
        np.empty(0, dtype=numpy_dtype(data_type)) if data_type in NUMERIC_TYPES else []
    )
    return CandidateSet(np.empty(0, dtype=np.uint64), values, data_type)


class ScanEngine:
    """Scan process regions and efficiently refine materialized candidates."""

    def __init__(self, backend: MemoryBackend) -> None:
        self._backend = backend

    def select_regions(self, opts: ScanOptions) -> list[MemoryRegion]:
        """Select and clip readable regions according to scan options."""
        selected: list[MemoryRegion] = []
        upper_exclusive = opts.address_max + 1
        for region in self._backend.regions():
            if not region.readable or (opts.writable_only and not region.writable):
                continue
            if region.type == _MEM_IMAGE and not opts.include_image:
                continue
            if region.type == _MEM_MAPPED and not opts.include_mapped:
                continue
            start = max(region.base, opts.address_min)
            end = min(region.end, upper_exclusive)
            if start >= end:
                continue
            selected.append(
                MemoryRegion(
                    base=start,
                    size=end - start,
                    protect=region.protect,
                    state=region.state,
                    type=region.type,
                    module=region.module,
                )
            )
        return selected

    def first_scan(
        self,
        req: ScanRequest,
        cancel: threading.Event,
        on_progress: Callable[[ScanProgress], None],
    ) -> CandidateSet | UnknownSnapshot:
        """Perform a first scan over selected regions."""
        req.validate()
        regions = self.select_regions(req.options)
        if req.mode is ScanMode.UNKNOWN_INITIAL:
            return self._capture_unknown(regions, req, cancel, on_progress)
        if req.mode in _RELATIVE_MODES:
            raise ValueParseError("Este modo necesita un escaneo anterior para poder comparar.")
        return self._scan_regions(regions, req, cancel, on_progress)

    def _scan_regions(
        self,
        regions: list[MemoryRegion],
        req: ScanRequest,
        cancel: threading.Event,
        on_progress: Callable[[ScanProgress], None],
    ) -> CandidateSet:
        opts = req.options
        if req.data_type in NUMERIC_TYPES:
            item_size = type_size(req.data_type)
            overlap = item_size - 1
            pattern = mask = None
        elif req.mode is ScanMode.AOB:
            assert req.value is not None
            pattern, mask = parse_aob(req.value)
            item_size = len(pattern)
            overlap = item_size - 1
        else:
            assert req.value is not None
            pattern = encode_value(req.data_type, req.value)
            mask = b"\xff" * len(pattern)
            item_size = len(pattern)
            overlap = item_size - 1
        total_bytes = sum(region.size for region in regions)
        reporter = _ProgressReporter(on_progress, total_bytes, len(regions))
        address_parts: list[NDArray[np.uint64]] = []
        numeric_parts: list[NDArray[Any]] = []
        byte_values: list[bytes] = []
        bytes_done = 0
        candidates = 0
        for region_index, region in enumerate(regions):
            offset = 0
            while offset < region.size:
                if cancel.is_set():
                    raise ScanCancelled()
                primary_size = min(opts.chunk_size, region.size - offset)
                read_size = min(primary_size + overlap, region.size - offset)
                target = bytearray(read_size)
                count = self._backend.read_into(region.base + offset, memoryview(target))
                usable = bytes(target[:count])
                accepted_primary = min(primary_size, count)
                if count >= item_size and accepted_primary:
                    if req.data_type in NUMERIC_TYPES:
                        for local_offsets, values in _numeric_slices(
                            usable,
                            region.base + offset,
                            req.data_type,
                            opts.alignment,
                            accepted_primary,
                        ):
                            indices = self._first_numeric_indices(values, req)
                            if indices.size:
                                matched_offsets = local_offsets[indices]
                                addresses = (region.base + offset + matched_offsets).astype(
                                    np.uint64, copy=False
                                )
                                address_parts.append(addresses)
                                numeric_parts.append(values[indices].copy())
                                candidates += int(indices.size)
                    else:
                        assert pattern is not None and mask is not None
                        case_sensitive = opts.case_sensitive or req.mode is ScanMode.AOB
                        search_raw = usable if case_sensitive else usable.lower()
                        search_pattern = pattern if case_sensitive else pattern.lower()
                        indices = kernel_aob(
                            np.frombuffer(search_raw, dtype=np.uint8), search_pattern, mask
                        )
                        indices = indices[indices < accepted_primary]
                        alignment = 1 if opts.alignment == 0 else opts.alignment
                        if alignment > 1:
                            absolute = region.base + offset + indices
                            indices = indices[absolute % alignment == 0]
                        if indices.size:
                            addresses = (region.base + offset + indices).astype(
                                np.uint64, copy=False
                            )
                            address_parts.append(addresses)
                            byte_values.extend(
                                usable[int(index) : int(index) + item_size] for index in indices
                            )
                            candidates += int(indices.size)
                    self._check_candidate_limit(candidates, opts.max_candidates)
                bytes_done += accepted_primary
                reporter.emit(region_index, bytes_done, candidates)
                offset += primary_size
            reporter.emit(region_index + 1, bytes_done, candidates)
        return self._combine_candidates(req.data_type, address_parts, numeric_parts, byte_values)

    @staticmethod
    def _first_numeric_indices(values: NDArray[Any], req: ScanRequest) -> NDArray[np.int64]:
        assert req.value is not None
        needle = parse_value(req.data_type, req.value)
        if req.mode is ScanMode.EXACT:
            return kernel_exact(values, needle, _tolerance(req))
        if req.mode is ScanMode.BETWEEN:
            assert req.value2 is not None
            return kernel_range(values, needle, parse_value(req.data_type, req.value2))
        if req.mode is ScanMode.GREATER_THAN:
            return np.flatnonzero(values > needle).astype(np.int64, copy=False)
        if req.mode is ScanMode.LESS_THAN:
            return np.flatnonzero(values < needle).astype(np.int64, copy=False)
        raise ValueParseError("Esta condición no es válida para un primer escaneo numérico.")

    @staticmethod
    def _check_candidate_limit(count: int, maximum: int) -> None:
        if count > maximum:
            raise ScanError(
                f"Demasiados candidatos (>{maximum}). Usa un valor más específico o reduce "
                "el rango de regiones."
            )

    @staticmethod
    def _combine_candidates(
        data_type: DataType,
        address_parts: list[NDArray[np.uint64]],
        numeric_parts: list[NDArray[Any]],
        byte_values: list[bytes],
    ) -> CandidateSet:
        if not address_parts:
            return _empty_candidates(data_type)
        addresses = np.concatenate(address_parts)
        order = np.argsort(addresses, kind="stable")
        addresses = addresses[order]
        keep = np.ones(addresses.size, dtype=np.bool_)
        keep[1:] = addresses[1:] != addresses[:-1]
        if data_type in NUMERIC_TYPES:
            values = np.concatenate(numeric_parts)[order][keep]
            return CandidateSet(addresses[keep], values, data_type)
        ordered_values = [byte_values[int(index)] for index in order]
        values_list = [
            value for value, retained in zip(ordered_values, keep, strict=True) if retained
        ]
        return CandidateSet(addresses[keep], values_list, data_type)

    def _capture_unknown(
        self,
        regions: list[MemoryRegion],
        req: ScanRequest,
        cancel: threading.Event,
        on_progress: Callable[[ScanProgress], None],
    ) -> UnknownSnapshot:
        opts = req.options
        budget = opts.unknown_budget_mb * (1 << 20)
        prioritized = sorted(
            regions,
            key=lambda region: (
                0
                if region.type == _MEM_PRIVATE and region.writable
                else 1
                if region.type == _MEM_IMAGE and region.writable
                else 2,
                region.base,
            ),
        )
        selected: list[MemoryRegion] = []
        skipped = 0
        remaining = budget
        for region in prioritized:
            if region.size <= remaining:
                selected.append(region)
                remaining -= region.size
            else:
                skipped += 1
        total_bytes = sum(region.size for region in selected)
        reporter = _ProgressReporter(on_progress, total_bytes, len(selected))
        chunks: list[tuple[int, bytes]] = []
        bytes_done = 0
        overlap = type_size(req.data_type) - 1
        for region_index, region in enumerate(selected):
            offset = 0
            while offset < region.size:
                if cancel.is_set():
                    raise ScanCancelled()
                primary_size = min(opts.chunk_size, region.size - offset)
                read_size = min(primary_size + overlap, region.size - offset)
                target = bytearray(read_size)
                count = self._backend.read_into(region.base + offset, memoryview(target))
                if count:
                    chunks.append((region.base + offset, bytes(target[:count])))
                accepted_primary = min(primary_size, count)
                bytes_done += accepted_primary
                reporter.emit(region_index, bytes_done, 0)
                offset += primary_size
            reporter.emit(region_index + 1, bytes_done, 0)
        return UnknownSnapshot(chunks, bytes_done, skipped)

    def refine(
        self,
        previous: CandidateSet | UnknownSnapshot,
        req: ScanRequest,
        cancel: threading.Event,
        on_progress: Callable[[ScanProgress], None],
    ) -> CandidateSet:
        """Refine candidates without rescanning every memory region."""
        req.validate()
        if req.mode is ScanMode.UNKNOWN_INITIAL:
            raise ValueParseError(
                "Valor desconocido inicial solo puede usarse en el primer escaneo."
            )
        if isinstance(previous, UnknownSnapshot):
            return self._refine_unknown(previous, req, cancel, on_progress)
        if previous.data_type is not req.data_type:
            raise ValueParseError("El tipo de dato debe coincidir con el escaneo anterior.")
        return self._refine_candidates(previous, req, cancel, on_progress)

    def _refine_candidates(
        self,
        previous: CandidateSet,
        req: ScanRequest,
        cancel: threading.Event,
        on_progress: Callable[[ScanProgress], None],
    ) -> CandidateSet:
        if not len(previous):
            return _empty_candidates(req.data_type)
        order = np.argsort(previous.addresses, kind="stable")
        sorted_addresses = previous.addresses[order]
        if req.data_type in NUMERIC_TYPES:
            value_size = type_size(req.data_type)
        elif req.value is not None:
            value_size = len(encode_value(req.data_type, req.value))
        else:
            value_size = max((len(value) for value in previous.values), default=1)
        groups: list[tuple[int, int]] = []
        start = 0
        for index in range(1, sorted_addresses.size):
            gap = int(sorted_addresses[index]) - int(sorted_addresses[index - 1])
            span = int(sorted_addresses[index]) + value_size - int(sorted_addresses[start])
            if gap > 4096 or span > 65536:
                groups.append((start, index))
                start = index
        groups.append((start, int(sorted_addresses.size)))
        total_bytes = sum(
            int(sorted_addresses[end - 1]) + value_size - int(sorted_addresses[start_index])
            for start_index, end in groups
        )
        reporter = _ProgressReporter(on_progress, total_bytes, len(groups))
        kept_addresses: list[int] = []
        current_numeric: list[Any] = []
        previous_numeric: list[Any] = []
        current_bytes: list[bytes] = []
        previous_bytes: list[bytes] = []
        bytes_done = 0
        sorted_old_values: NDArray[Any] | list[bytes]
        if isinstance(previous.values, np.ndarray):
            sorted_old_values = previous.values[order]
        else:
            sorted_old_values = [previous.values[int(index)] for index in order]
        for group_index, (group_start, group_end) in enumerate(groups):
            if cancel.is_set():
                raise ScanCancelled()
            read_base = int(sorted_addresses[group_start])
            read_end = int(sorted_addresses[group_end - 1]) + value_size
            target = bytearray(read_end - read_base)
            count = self._backend.read_into(read_base, memoryview(target))
            bytes_done += count
            for index in range(group_start, group_end):
                address = int(sorted_addresses[index])
                relative = address - read_base
                if relative + value_size > count:
                    continue
                raw = bytes(target[relative : relative + value_size])
                kept_addresses.append(address)
                if req.data_type in NUMERIC_TYPES:
                    current_numeric.append(
                        np.frombuffer(raw, dtype=numpy_dtype(req.data_type), count=1)[0]
                    )
                    assert isinstance(sorted_old_values, np.ndarray)
                    previous_numeric.append(sorted_old_values[index])
                else:
                    current_bytes.append(raw)
                    assert isinstance(sorted_old_values, list)
                    previous_bytes.append(sorted_old_values[index])
            reporter.emit(group_index + 1, bytes_done, len(kept_addresses))
        addresses = np.asarray(kept_addresses, dtype=np.uint64)
        if req.data_type in NUMERIC_TYPES:
            current = np.asarray(current_numeric, dtype=numpy_dtype(req.data_type))
            old = np.asarray(previous_numeric, dtype=numpy_dtype(req.data_type))
            mask = self._numeric_refine_mask(current, old, req)
            self._check_candidate_limit(int(np.count_nonzero(mask)), req.options.max_candidates)
            return CandidateSet(addresses[mask], current[mask], req.data_type)
        byte_mask = self._byte_refine_mask(current_bytes, previous_bytes, req)
        retained = [value for value, keep in zip(current_bytes, byte_mask, strict=True) if keep]
        bool_mask = np.asarray(byte_mask, dtype=np.bool_)
        self._check_candidate_limit(len(retained), req.options.max_candidates)
        return CandidateSet(addresses[bool_mask], retained, req.data_type)

    @staticmethod
    def _numeric_refine_mask(
        current: NDArray[Any], old: NDArray[Any], req: ScanRequest
    ) -> NDArray[np.bool_]:
        tol = _tolerance(req)
        if req.mode in _RELATIVE_MODES:
            delta = None
            if req.value is not None:
                delta = parse_value(req.data_type, req.value)
            return kernel_compare(current, old, req.mode, delta, tol)
        assert req.value is not None
        needle = parse_value(req.data_type, req.value)
        if req.mode is ScanMode.EXACT:
            selected = kernel_exact(current, needle, tol)
        elif req.mode is ScanMode.BETWEEN:
            assert req.value2 is not None
            selected = kernel_range(current, needle, parse_value(req.data_type, req.value2))
        elif req.mode is ScanMode.GREATER_THAN:
            selected = np.flatnonzero(current > needle).astype(np.int64, copy=False)
        elif req.mode is ScanMode.LESS_THAN:
            selected = np.flatnonzero(current < needle).astype(np.int64, copy=False)
        else:
            raise ValueParseError("La condición no es válida para este refinamiento.")
        mask = np.zeros(current.size, dtype=np.bool_)
        mask[selected] = True
        return mask

    @staticmethod
    def _byte_refine_mask(current: list[bytes], old: list[bytes], req: ScanRequest) -> list[bool]:
        if req.mode in {ScanMode.AOB, ScanMode.TEXT}:
            assert req.value is not None
            if req.mode is ScanMode.AOB:
                pattern, pattern_mask = parse_aob(req.value)
            else:
                pattern = encode_value(req.data_type, req.value)
                pattern_mask = b"\xff" * len(pattern)
            case_sensitive = req.options.case_sensitive or req.mode is ScanMode.AOB
            if not case_sensitive:
                pattern = pattern.lower()
            result: list[bool] = []
            for value in current:
                comparable = value if case_sensitive else value.lower()
                result.append(
                    len(comparable) >= len(pattern)
                    and all(
                        not mask or comparable[index] == pattern[index]
                        for index, mask in enumerate(pattern_mask)
                    )
                )
            return result
        if req.mode is ScanMode.CHANGED:
            return [
                current_value != old_value
                for current_value, old_value in zip(current, old, strict=True)
            ]
        if req.mode is ScanMode.UNCHANGED:
            return [
                current_value == old_value
                for current_value, old_value in zip(current, old, strict=True)
            ]
        raise ValueParseError("La condición no es válida para datos de longitud variable.")

    def _refine_unknown(
        self,
        previous: UnknownSnapshot,
        req: ScanRequest,
        cancel: threading.Event,
        on_progress: Callable[[ScanProgress], None],
    ) -> CandidateSet:
        if req.data_type not in NUMERIC_TYPES or req.mode not in _RELATIVE_MODES:
            raise ValueParseError(
                "Un escaneo de valor desconocido debe refinarse con una comparación numérica."
            )
        total_bytes = sum(len(raw) for _, raw in previous.chunks)
        reporter = _ProgressReporter(on_progress, total_bytes, len(previous.chunks))
        addresses_parts: list[NDArray[np.uint64]] = []
        values_parts: list[NDArray[Any]] = []
        bytes_done = 0
        candidates = 0
        for chunk_index, (base, old_raw) in enumerate(previous.chunks):
            if cancel.is_set():
                raise ScanCancelled()
            target = bytearray(len(old_raw))
            count = self._backend.read_into(base, memoryview(target))
            usable = min(count, len(old_raw))
            if usable >= type_size(req.data_type):
                current_raw = bytes(target[:usable])
                old_usable = old_raw[:usable]
                for offsets, current in _numeric_slices(
                    current_raw, base, req.data_type, req.options.alignment, usable
                ):
                    stride = (
                        int(offsets[1] - offsets[0])
                        if offsets.size > 1
                        else type_size(req.data_type)
                    )
                    old = np.ndarray(
                        shape=current.shape,
                        dtype=numpy_dtype(req.data_type),
                        buffer=old_usable,
                        offset=int(offsets[0]),
                        strides=(stride,),
                    )
                    mask = self._numeric_refine_mask(current, old, req)
                    if np.any(mask):
                        addresses_parts.append((base + offsets[mask]).astype(np.uint64, copy=False))
                        values_parts.append(current[mask].copy())
                        candidates += int(np.count_nonzero(mask))
                        self._check_candidate_limit(candidates, req.options.max_candidates)
            bytes_done += usable
            reporter.emit(chunk_index + 1, bytes_done, candidates)
        return self._combine_candidates(req.data_type, addresses_parts, values_parts, [])
