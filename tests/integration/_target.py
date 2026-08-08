"""Robust client for the deterministic integration target process."""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Self

_ROOT = Path(__file__).resolve().parents[2]
_TARGET = _ROOT / "tests" / "fixtures" / "target_process.py"
_PYTHON = Path(sys.base_prefix) / ("python.exe" if sys.platform == "win32" else "bin/python")
if not _PYTHON.exists():
    _PYTHON = Path(sys.executable)


class TargetProcess:
    """Manage the target child and provide timeout-bounded JSON commands."""

    def __init__(self, process: subprocess.Popen[str]) -> None:
        self.process = process
        self._messages: queue.Queue[dict[str, Any] | BaseException | None] = queue.Queue()
        self._reader = threading.Thread(
            target=self._read_output,
            name=f"target-process-output-{process.pid}",
            daemon=True,
        )
        self._reader.start()
        self.manifest = self.receive(timeout=10.0)
        if self.manifest.get("event") != "ready" or self.manifest.get("pid") != process.pid:
            self.close()
            raise RuntimeError(f"Invalid target startup payload: {self.manifest!r}")

    @classmethod
    def start(cls) -> Self:
        """Start an unbuffered child from the repository fixture script."""
        process = subprocess.Popen(
            [str(_PYTHON), "-u", str(_TARGET)],
            cwd=_ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            return cls(process)
        except BaseException:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5.0)
            raise

    @property
    def pid(self) -> int:
        return self.process.pid

    def address(self, name: str) -> int:
        """Return one integer address from the startup manifest."""
        value = self.manifest.get(name)
        if not isinstance(value, int):
            raise AssertionError(f"Target manifest has no integer {name!r}: {value!r}")
        return value

    def command(self, command: str, *, timeout: float = 5.0) -> dict[str, Any]:
        """Send one command and receive exactly one JSON response."""
        if self.process.poll() is not None:
            raise RuntimeError(f"Target process exited with code {self.process.returncode}")
        stream = self.process.stdin
        if stream is None:
            raise RuntimeError("Target process stdin is unavailable")
        stream.write(f"{command}\n")
        stream.flush()
        return self.receive(timeout=timeout)

    def receive(self, *, timeout: float) -> dict[str, Any]:
        """Receive one parsed line without allowing a pipe read to hang the suite."""
        try:
            message = self._messages.get(timeout=timeout)
        except queue.Empty:
            code = self.process.poll()
            raise TimeoutError(
                f"Target process did not respond within {timeout:.1f}s; exit_code={code}"
            ) from None
        if isinstance(message, BaseException):
            raise RuntimeError("Target output reader failed") from message
        if message is None:
            error = ""
            if self.process.poll() is not None and self.process.stderr is not None:
                error = self.process.stderr.read().strip()
            raise RuntimeError(
                "Target output closed unexpectedly; "
                f"exit_code={self.process.poll()}; stderr={error!r}"
            )
        return message

    def kill(self) -> None:
        """Kill the child and wait for its process handle to become signaled."""
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=5.0)
        self._reader.join(timeout=5.0)

    def close(self) -> None:
        """Request graceful exit, then force cleanup on every failure path."""
        if self.process.poll() is None:
            try:
                self.command("quit", timeout=2.0)
            except (BrokenPipeError, OSError, RuntimeError, TimeoutError):
                self.process.terminate()
        try:
            self.process.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5.0)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()
        self._reader.join(timeout=5.0)
        if self._reader.is_alive():
            raise RuntimeError("Target output reader did not stop")

    def _read_output(self) -> None:
        stream = self.process.stdout
        if stream is None:
            self._messages.put(RuntimeError("Target process stdout is unavailable"))
            return
        try:
            for line in stream:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    self._messages.put(exc)
                    continue
                if not isinstance(payload, dict):
                    self._messages.put(TypeError(f"Expected a JSON object, got {payload!r}"))
                    continue
                self._messages.put(payload)
        except BaseException as exc:
            self._messages.put(exc)
        finally:
            self._messages.put(None)
