"""Materialized scan session state, filtering, and pagination."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

import numpy as np
from numpy.typing import NDArray

from mempilot.core.backend import MemoryBackend, MemoryRegion, ProcessIdentity
from mempilot.core.data_types import NUMERIC_TYPES, DataType, decode_value, numpy_dtype, type_size
from mempilot.core.exceptions import MemoryReadError
from mempilot.core.scanner import (
    CandidateSet,
    ScanMode,
    ScanOptions,
    ScanRequest,
    UnknownSnapshot,
)
from mempilot.i18n import Language, get_language, t


class SessionState(StrEnum):
    NEW = "new"
    SCANNING = "scanning"
    READY = "ready"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass(slots=True)
class RefinementRecord:
    index: int
    mode: ScanMode
    value: str | None
    value2: str | None
    candidates_before: int
    candidates_after: int
    timestamp: datetime
    duration_s: float


@dataclass(slots=True)
class CandidateRow:
    address: int
    current: str
    previous: str
    data_type: DataType
    region: str
    protection: str
    change_rate: float
    readable: bool
    writable: bool


@dataclass(frozen=True, slots=True)
class OrderSpec:
    column: str = "address"
    descending: bool = False


@dataclass(frozen=True, slots=True)
class FilterSpec:
    text: str = ""
    address_min: int | None = None
    address_max: int | None = None
    module: str | None = None


def _display_scalar(value: Any, data_type: DataType) -> str:
    if data_type is DataType.BOOL:
        return "true" if bool(value) else "false"
    item = value.item() if isinstance(value, np.generic) else value
    return str(item)


@dataclass(slots=True)
class ScanSession:
    identity: ProcessIdentity
    data_type: DataType
    options: ScanOptions
    session_id: str = field(default_factory=lambda: uuid4().hex[:12], init=False)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC), init=False)
    state: SessionState = field(default=SessionState.NEW, init=False)
    result: CandidateSet | UnknownSnapshot | None = field(default=None, init=False)
    previous_values: NDArray[Any] | list[bytes] | None = field(default=None, init=False)
    regions_scanned: int = field(default=0, init=False)
    bytes_scanned: int = field(default=0, init=False)
    history: list[RefinementRecord] = field(default_factory=list, init=False)
    error: str | None = field(default=None, init=False)
    memory_regions: list[MemoryRegion] = field(default_factory=list, init=False)
    last_mode: ScanMode | None = field(default=None, init=False)
    last_duration_s: float = field(default=0.0, init=False)
    _change_rates: dict[int, float] = field(default_factory=dict, init=False, repr=False)

    def total(self) -> int:
        """Return the number of materialized candidates."""
        return len(self.result) if isinstance(self.result, CandidateSet) else 0

    def set_first_result(
        self,
        result: CandidateSet | UnknownSnapshot,
        request: ScanRequest,
        *,
        regions_scanned: int,
        bytes_scanned: int,
        duration_s: float,
        memory_regions: Sequence[MemoryRegion] = (),
    ) -> None:
        """Store a completed first scan and its display metadata."""
        self.result = result
        self.previous_values = None
        self.regions_scanned = regions_scanned
        self.bytes_scanned = bytes_scanned
        self.memory_regions = list(memory_regions)
        self.last_mode = request.mode
        self.last_duration_s = duration_s
        self.error = None
        self.state = SessionState.READY

    def set_refined_result(
        self,
        result: CandidateSet,
        request: ScanRequest,
        *,
        duration_s: float,
    ) -> None:
        """Replace candidates and append one refinement history record."""
        before = self.total()
        old_result = self.result
        old_by_address: dict[int, Any] = {}
        if isinstance(old_result, CandidateSet):
            if isinstance(old_result.values, np.ndarray):
                old_by_address = {
                    int(address): old_result.values[index]
                    for index, address in enumerate(old_result.addresses)
                }
            else:
                old_by_address = {
                    int(address): old_result.values[index]
                    for index, address in enumerate(old_result.addresses)
                }
        elif isinstance(old_result, UnknownSnapshot) and isinstance(result.values, np.ndarray):
            chunks = sorted(old_result.chunks)
            chunk_bases = np.asarray([base for base, _raw in chunks], dtype=np.uint64)
            size = type_size(self.data_type)
            for address_value in result.addresses:
                address = int(address_value)
                position = int(np.searchsorted(chunk_bases, address, side="right")) - 1
                if position < 0:
                    continue
                base, raw = chunks[position]
                relative = address - base
                if relative + size <= len(raw):
                    old_by_address[address] = np.frombuffer(
                        raw, dtype=numpy_dtype(self.data_type), count=1, offset=relative
                    )[0]
        if isinstance(result.values, np.ndarray):
            self.previous_values = np.asarray(
                [
                    old_by_address.get(int(address), result.values[index])
                    for index, address in enumerate(result.addresses)
                ],
                dtype=result.values.dtype,
            )
        else:
            self.previous_values = [
                old_by_address.get(int(address), result.values[index])
                for index, address in enumerate(result.addresses)
            ]
        self.result = result
        self.last_mode = request.mode
        self.last_duration_s = duration_s
        self.state = SessionState.READY
        self.error = None
        self.history.append(
            RefinementRecord(
                index=len(self.history) + 1,
                mode=request.mode,
                value=request.value,
                value2=request.value2,
                candidates_before=before,
                candidates_after=len(result),
                timestamp=datetime.now(UTC),
                duration_s=duration_s,
            )
        )

    def page(
        self,
        offset: int,
        limit: int,
        order: OrderSpec,
        filt: FilterSpec,
    ) -> list[CandidateRow]:
        """Return a filtered, ordered page without materializing every row object."""
        if offset < 0 or limit < 0:
            raise ValueError(t("results.offset_limit_nonnegative"))
        if not isinstance(self.result, CandidateSet) or not len(self.result) or limit == 0:
            return []
        result = self.result
        count = len(result)
        addresses = result.addresses
        indices = np.arange(count, dtype=np.int64)
        selected = np.ones(count, dtype=np.bool_)
        if filt.address_min is not None:
            selected &= addresses >= filt.address_min
        if filt.address_max is not None:
            selected &= addresses <= filt.address_max
        current: NDArray[np.str_] | None = None
        regions: NDArray[np.str_] | None = None
        if filt.module:
            regions = self._region_labels(addresses)
            selected &= np.char.startswith(np.char.lower(regions), filt.module.casefold())
        if filt.text:
            needle = filt.text.casefold()
            current = self._display_values(result.values)
            if regions is None:
                regions = self._region_labels(addresses)
            address_text = np.asarray([f"0x{int(address):016X}" for address in addresses])
            haystack = np.char.add(np.char.add(address_text, " "), current)
            haystack = np.char.add(np.char.add(haystack, " "), regions)
            selected &= np.char.find(np.char.lower(haystack), needle) >= 0
        indices = indices[selected]
        if not indices.size:
            return []
        if order.column in {"address", "Dirección"}:
            keys: NDArray[Any] = addresses[indices]
        elif order.column in {"value", "current", "Valor"}:
            if isinstance(result.values, np.ndarray):
                keys = result.values[indices]
            else:
                if current is None:
                    current = self._display_values(result.values)
                keys = current[indices]
        elif order.column in {"change_rate", "Cambios"}:
            keys = np.asarray(
                [self._change_rates.get(int(addresses[index]), 0.0) for index in indices]
            )
        elif order.column in {"region", "Región/Módulo"}:
            if regions is None:
                regions = self._region_labels(addresses)
            keys = regions[indices]
        else:
            raise ValueError(t("results.unknown_order_column", column=order.column))
        sorted_positions = np.argsort(keys, kind="stable")
        if order.descending:
            sorted_positions = sorted_positions[::-1]
        page_indices = indices[sorted_positions][offset : offset + limit]
        return [self._make_row(int(index)) for index in page_indices]

    def _display_values(self, values: NDArray[Any] | list[bytes]) -> NDArray[np.str_]:
        if isinstance(values, np.ndarray):
            return np.asarray([_display_scalar(value, self.data_type) for value in values])
        return np.asarray([decode_value(self.data_type, value) for value in values])

    def _region_labels(self, addresses: NDArray[np.uint64]) -> NDArray[np.str_]:
        return np.asarray([self._region_label(int(address))[0] for address in addresses])

    def _make_row(self, index: int) -> CandidateRow:
        assert isinstance(self.result, CandidateSet)
        address = int(self.result.addresses[index])
        previous = ""
        if self.previous_values is not None and index < len(self.previous_values):
            if isinstance(self.previous_values, np.ndarray):
                previous = _display_scalar(self.previous_values[index], self.data_type)
            else:
                previous = decode_value(self.data_type, self.previous_values[index])
        label, region = self._region_label(address)
        if isinstance(self.result.values, np.ndarray):
            current = _display_scalar(self.result.values[index], self.data_type)
        else:
            current = decode_value(self.data_type, self.result.values[index])
        return CandidateRow(
            address=address,
            current=current,
            previous=previous,
            data_type=self.data_type,
            region=label,
            protection=region.protect_text() if region else "—",
            change_rate=self._change_rates.get(address, 0.0),
            readable=region.readable if region else False,
            writable=region.writable if region else False,
        )

    def _region_label(self, address: int) -> tuple[str, MemoryRegion | None]:
        for region in self.memory_regions:
            if region.base <= address < region.end:
                if region.module:
                    module_base = min(
                        candidate.base
                        for candidate in self.memory_regions
                        if candidate.module
                        and candidate.module.casefold() == region.module.casefold()
                    )
                    return f"{region.module}+0x{address - module_base:X}", region
                return f"{region.type_text().casefold()} 0x{region.base:016X}", region
        return f"privada 0x{address:016X}", None

    def refresh_values(self, backend: MemoryBackend, addresses: Sequence[int]) -> dict[int, str]:
        """Read and format selected candidate addresses, dropping failed reads."""
        if not isinstance(self.result, CandidateSet):
            return {}
        index_by_address = {
            int(address): index for index, address in enumerate(self.result.addresses)
        }
        refreshed: dict[int, str] = {}
        displayed_values = self._display_values(self.result.values)
        for address in addresses:
            index = index_by_address.get(address)
            if index is None:
                continue
            if self.data_type in NUMERIC_TYPES:
                size = type_size(self.data_type)
            else:
                assert isinstance(self.result.values, list)
                size = len(self.result.values[index])
            try:
                raw = backend.read(address, size)
            except MemoryReadError:
                continue
            if len(raw) < size:
                continue
            text = decode_value(self.data_type, raw)
            refreshed[address] = text
            old_text = displayed_values[index]
            changed = text != old_text
            old_rate = self._change_rates.get(address, 0.0)
            self._change_rates[address] = 0.9 * old_rate + (0.1 if changed else 0.0)
            if isinstance(self.result.values, np.ndarray):
                self.result.values[index] = np.frombuffer(
                    raw, dtype=numpy_dtype(self.data_type), count=1
                )[0]
            else:
                self.result.values[index] = raw
        return refreshed

    def stats(self) -> dict[str, str]:
        """Return formatted statistics for the scan panel."""
        total = f"{self.total():,}"
        if get_language() is Language.SPANISH:
            total = total.replace(",", ".")
        return {
            t("scan.stats.candidates"): total,
            t("scan.stats.regions"): str(self.regions_scanned),
            t("scan.stats.bytes"): self._format_bytes(self.bytes_scanned),
            t("scan.stats.duration"): f"{self.last_duration_s:.2f} s",
            t("scan.stats.refinements"): str(len(self.history)),
            t("scan.stats.type"): self.data_type.value,
            t("scan.stats.last_condition"): self.last_mode.value if self.last_mode else "—",
        }

    @staticmethod
    def _format_bytes(size: int) -> str:
        value = float(size)
        for suffix in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024.0 or suffix == "TB":
                decimals = 0 if suffix == "B" else 1
                formatted = f"{value:.{decimals}f} {suffix}"
                return (
                    formatted.replace(".", ",") if get_language() is Language.SPANISH else formatted
                )
            value /= 1024.0
        raise AssertionError("unreachable")
