"""Safe process discovery and identity validation."""

from __future__ import annotations

import os
from dataclasses import dataclass

import psutil

from mempilot.core.backend import Architecture, ProcessIdentity
from mempilot.core.exceptions import ProcessNotAllowedError, ProcessNotFoundError
from mempilot.core.win32_api import PROCESS_QUERY_INFORMATION, PROCESS_VM_READ, kernel32
from mempilot.core.win32_backend import architecture_from_handle
from mempilot.i18n import t

NEVER_ATTACH = {
    "system",
    "registry",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "lsaiso.exe",
    "msmpeng.exe",
    "securityhealthservice.exe",
    "memcompression",
}
HIDDEN_BY_DEFAULT = NEVER_ATTACH | {
    "svchost.exe",
    "dwm.exe",
    "fontdrvhost.exe",
    "wmiprvse.exe",
    "spoolsv.exe",
    "audiodg.exe",
    "sihost.exe",
    "ctfmon.exe",
    "runtimebroker.exe",
    "searchindexer.exe",
}
_SYSTEM_ACCOUNTS = {"system", "local service", "network service"}


@dataclass(frozen=True, slots=True)
class ProcessEntry:
    """Process row exposed to the process picker."""

    pid: int
    name: str
    path: str | None
    architecture: Architecture
    username: str | None
    is_system: bool
    can_attach: bool
    note: str


class ProcessService:
    """Enumerate user processes and create PID-reuse-safe identities."""

    def list_processes(
        self,
        query: str = "",
        include_system: bool = False,
    ) -> list[ProcessEntry]:
        """Return filtered processes without dropping entries whose path is inaccessible."""
        normalized_query = query.strip().casefold()
        numeric_pid = int(normalized_query) if normalized_query.isdecimal() else None
        own_pid = os.getpid()
        entries: list[ProcessEntry] = []

        for process in psutil.process_iter():
            pid = int(process.pid)
            if numeric_pid is not None and pid != numeric_pid:
                continue
            try:
                name = process.name()
            except (psutil.NoSuchProcess, psutil.ZombieProcess):
                continue
            except psutil.AccessDenied:
                name = "desconocido"
            normalized_name = name.casefold()
            if numeric_pid is None and normalized_query not in normalized_name:
                continue

            protected = self._is_never_attach(pid, normalized_name)
            username = self._username(process)
            system_account = self._is_system_account(username)
            hidden = (
                protected
                or normalized_name in HIDDEN_BY_DEFAULT
                or pid == own_pid
                or system_account
            )
            if hidden and not include_system:
                continue

            path, note = self._path_and_note(process)
            if protected or pid == own_pid:
                architecture = Architecture.UNKNOWN
                can_attach = False
                note = self._append_note(note, t("process.note.protected"))
            else:
                architecture, can_attach = self._probe_process(pid)
                if not can_attach:
                    note = self._append_note(note, t("process.note.unavailable"))
            entries.append(
                ProcessEntry(
                    pid=pid,
                    name=name,
                    path=path,
                    architecture=architecture,
                    username=username,
                    is_system=hidden,
                    can_attach=can_attach,
                    note=note,
                )
            )

        entries.sort(key=lambda entry: (entry.name.casefold(), entry.pid))
        return entries

    def identity(self, pid: int) -> ProcessIdentity:
        """Build a stable process identity or reject protected targets."""
        if pid in {0, 4, os.getpid()}:
            raise ProcessNotAllowedError(t("process.pid_protected", pid=pid))
        try:
            process = psutil.Process(pid)
            name = process.name()
            create_time = float(process.create_time())
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            raise ProcessNotFoundError(t("process.pid_missing", pid=pid)) from None
        except psutil.AccessDenied:
            raise ProcessNotAllowedError(t("process.pid_uncheckable", pid=pid)) from None

        if self._is_never_attach(pid, name.casefold()):
            raise ProcessNotAllowedError(t("process.name_protected", name=name, pid=pid))
        try:
            path = process.exe() or None
        except psutil.AccessDenied:
            path = None
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            raise ProcessNotFoundError(t("process.pid_finished", pid=pid)) from None
        architecture, _ = self._probe_process(pid)
        return ProcessIdentity(
            pid=pid,
            name=name,
            create_time=create_time,
            path=path,
            architecture=architecture,
        )

    def is_alive(self, identity: ProcessIdentity) -> bool:
        """Check both PID existence and creation time to prevent PID-reuse confusion."""
        try:
            observed = psutil.Process(identity.pid)
            return observed.is_running() and float(observed.create_time()) == identity.create_time
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            return False

    @staticmethod
    def _is_never_attach(pid: int, normalized_name: str) -> bool:
        return pid in {0, 4} or normalized_name in NEVER_ATTACH

    @staticmethod
    def _username(process: psutil.Process) -> str | None:
        try:
            return process.username() or None
        except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
            return None

    @staticmethod
    def _path_and_note(process: psutil.Process) -> tuple[str | None, str]:
        try:
            return process.exe() or None, ""
        except psutil.AccessDenied:
            return None, t("process.note.path_inaccessible")
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return None, t("process.note.finished")

    @staticmethod
    def _is_system_account(username: str | None) -> bool:
        if username is None:
            return False
        account = username.rsplit("\\", maxsplit=1)[-1].casefold()
        return account in _SYSTEM_ACCOUNTS

    @staticmethod
    def _append_note(note: str, addition: str) -> str:
        return f"{note}; {addition}" if note else addition

    @staticmethod
    def _probe_process(pid: int) -> tuple[Architecture, bool]:
        access = PROCESS_QUERY_INFORMATION | PROCESS_VM_READ
        raw_handle = kernel32.OpenProcess(access, False, pid)
        if not raw_handle:
            return Architecture.UNKNOWN, False
        handle = int(raw_handle)
        try:
            return architecture_from_handle(handle), True
        finally:
            kernel32.CloseHandle(handle)
