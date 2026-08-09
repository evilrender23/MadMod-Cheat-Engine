"""Process-bound trainer catalogs and reversible trick definitions."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.data_types import DataType
from mempilot.core.exceptions import TrainerError
from mempilot.core.pointer_chain import PointerChain
from mempilot.core.watcher import WatchEntry, WatchSpec
from mempilot.logging_setup import redact_secrets


class TrickMode(StrEnum):
    """Supported reversible trainer behaviors."""

    FREEZE = "freeze"
    WRITE_PAIR = "write_pair"


class TrainerTrick(BaseModel):
    """One process-bound trick with a persistable addressing strategy."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1, max_length=80)
    data_type: DataType
    address_mode: Literal["absolute", "module_offset", "pointer_chain"]
    address: int | None = Field(default=None, ge=0)
    module: str | None = None
    offset: int | None = None
    chain: PointerChain | None = None
    enabled_value: str
    disabled_value: str | None = None
    mode: TrickMode = TrickMode.FREEZE
    interval_ms: int = Field(default=100, ge=50, le=5000)
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_contract(self) -> TrainerTrick:
        """Reject ambiguous addresses and non-reversible write pairs."""
        if not self.name.strip():
            raise ValueError("El nombre del truco no puede estar vacío.")
        if self.address_mode == "absolute":
            valid = self.address is not None and self.module is None and self.chain is None
        elif self.address_mode == "module_offset":
            valid = (
                bool(self.module and self.module.strip())
                and self.offset is not None
                and self.address is None
                and self.chain is None
            )
        else:
            valid = self.chain is not None and self.address is None and self.module is None
        if not valid:
            raise ValueError("La dirección persistida del truco es ambigua o está incompleta.")
        if self.mode is TrickMode.WRITE_PAIR and self.disabled_value is None:
            raise ValueError("Un truco de escritura reversible necesita un valor desactivado.")
        self.name = self.name.strip()
        self.notes = self.notes.strip()
        return self

    def watch_spec(self) -> WatchSpec:
        """Build the runtime watch used to activate this trick through AppController."""
        return WatchSpec(
            label=self.name,
            data_type=self.data_type,
            address=self.address,
            module=self.module,
            offset=self.offset,
            chain=self.chain,
            interval_ms=self.interval_ms,
            notes=self.notes,
        )


class TrainerCatalog(BaseModel):
    """Versioned trainer catalog stored below a process-specific directory."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    process_name: str
    architecture: Architecture
    created_at: datetime
    updated_at: datetime
    tricks: list[TrainerTrick] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TrainerTrickState:
    """Runtime activation state paired with one persisted trick."""

    trick: TrainerTrick
    active: bool


class TrainerService:
    """Atomically persist one trainer catalog per executable name."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def catalog_path(self, process_name: str) -> Path:
        """Return a confined path whose directory remains recognizable to the user."""
        normalized = unicodedata.normalize("NFKC", Path(process_name).name).strip()
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", normalized).strip(" ._") or "proceso"
        digest = hashlib.sha256(normalized.casefold().encode("utf-8")).hexdigest()[:8]
        return self.root / f"{safe[:64]}-{digest}" / "trainer.json"

    def load(self, identity: ProcessIdentity) -> TrainerCatalog:
        """Load the current process catalog or return an empty compatible catalog."""
        path = self.catalog_path(identity.name)
        if not path.exists():
            now = datetime.now(UTC)
            return TrainerCatalog(
                process_name=identity.name,
                architecture=identity.architecture,
                created_at=now,
                updated_at=now,
            )
        try:
            catalog = TrainerCatalog.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise TrainerError(
                "El trainer guardado no es válido o usa una versión incompatible."
            ) from exc
        if catalog.process_name.casefold() != identity.name.casefold():
            raise TrainerError("El trainer guardado pertenece a otro proceso.")
        if catalog.architecture is not identity.architecture:
            raise TrainerError("La arquitectura del trainer no coincide con el proceso adjunto.")
        return catalog

    def save_trick(
        self,
        identity: ProcessIdentity,
        watch: WatchEntry,
        *,
        name: str,
        enabled_value: str,
        disabled_value: str | None,
        mode: TrickMode,
        interval_ms: int,
        notes: str,
    ) -> TrainerTrick:
        """Insert or replace a named trick while preserving its stable identifier."""
        if mode is TrickMode.WRITE_PAIR and disabled_value is None:
            raise TrainerError("Un truco de escritura reversible necesita un valor desactivado.")
        catalog = self.load(identity)
        previous = next(
            (item for item in catalog.tricks if item.name.casefold() == name.strip().casefold()),
            None,
        )
        try:
            trick = TrainerTrick(
                id=previous.id if previous is not None else uuid4().hex[:12],
                name=name,
                data_type=watch.data_type,
                address_mode=watch.address_mode,
                address=watch.address,
                module=watch.module,
                offset=watch.offset,
                chain=watch.chain,
                enabled_value=enabled_value,
                disabled_value=disabled_value,
                mode=mode,
                interval_ms=interval_ms,
                notes=notes,
            )
        except ValidationError as exc:
            raise TrainerError(
                "El truco no es válido. Revisa el nombre, la dirección y los valores."
            ) from exc
        catalog.tricks = [item for item in catalog.tricks if item.id != trick.id]
        catalog.tricks.append(trick)
        catalog.updated_at = datetime.now(UTC)
        self._save(catalog, self.catalog_path(identity.name))
        return trick

    def update_trick_values(
        self,
        identity: ProcessIdentity,
        trick_id: str,
        *,
        enabled_value: str,
        disabled_value: str | None,
    ) -> TrainerTrick:
        """Persist user-edited activation values without changing the address contract."""
        catalog = self.load(identity)
        index = next(
            (index for index, item in enumerate(catalog.tricks) if item.id == trick_id),
            None,
        )
        if index is None:
            raise TrainerError(f"No existe el truco guardado {trick_id}.")
        original = catalog.tricks[index]
        try:
            updated = TrainerTrick.model_validate(
                {
                    **original.model_dump(),
                    "enabled_value": enabled_value,
                    "disabled_value": disabled_value,
                }
            )
        except ValidationError as exc:
            raise TrainerError(
                "Los valores del truco no son válidos. Revisa el valor activado y desactivado."
            ) from exc
        catalog.tricks[index] = updated
        catalog.updated_at = datetime.now(UTC)
        self._save(catalog, self.catalog_path(identity.name))
        return updated

    def find(self, identity: ProcessIdentity, trick_id: str) -> TrainerTrick:
        """Return one exact trick from the attached process catalog."""
        trick = next((item for item in self.load(identity).tricks if item.id == trick_id), None)
        if trick is None:
            raise TrainerError(f"No existe el truco guardado {trick_id}.")
        return trick

    @staticmethod
    def _save(catalog: TrainerCatalog, path: Path) -> None:
        temporary = path.with_name(f"{path.name}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            serialized = (
                redact_secrets(catalog.model_dump_json(indent=2, ensure_ascii=False)) + "\n"
            )
            temporary.write_text(serialized, encoding="utf-8")
            temporary.replace(path)
        except OSError as exc:
            raise TrainerError(
                f"No se pudo guardar el trainer en {path}. Comprueba la carpeta y los permisos."
            ) from exc
        finally:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
