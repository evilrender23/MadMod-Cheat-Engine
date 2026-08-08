"""Deterministic child process used by real Win32 integration tests."""

from __future__ import annotations

import ctypes
import json
import os
import sys
from typing import Any


class TargetState:
    """Own stable ctypes allocations and mutate only their values."""

    def __init__(self) -> None:
        self.health = (ctypes.c_int32 * 8)(*[100] * 8)
        self.coins = ctypes.c_int32(500)
        self.speed = ctypes.c_float(1.0)
        self.stamina = ctypes.c_double(75.0)
        self.alive = ctypes.c_bool(True)
        self.player_name = ctypes.create_unicode_buffer("PlayerOne", 64)
        self.player_tag = ctypes.create_string_buffer(b"MEMPILOT-LAB", 32)
        self.marker = (ctypes.c_ubyte * 16)(
            0x4D,
            0x45,
            0x4D,
            0x50,
            0xDE,
            0xAD,
            0xBE,
            0xEF,
            0x11,
            0x22,
            0x33,
            0x44,
            0x55,
            0x66,
            0x77,
            0x88,
        )
        self.slow_scan_buffer = (ctypes.c_ubyte * (32 << 20))()

    def manifest(self) -> dict[str, int | str]:
        """Publish all stable addresses needed by the parent tests."""
        health_address = ctypes.addressof(self.health)
        scan_min = health_address
        scan_max = health_address + ctypes.sizeof(self.health) - 1
        slow_min = ctypes.addressof(self.slow_scan_buffer)
        return {
            "event": "ready",
            "pid": os.getpid(),
            "health": health_address,
            "coins": ctypes.addressof(self.coins),
            "speed": ctypes.addressof(self.speed),
            "stamina": ctypes.addressof(self.stamina),
            "alive": ctypes.addressof(self.alive),
            "player_name": ctypes.addressof(self.player_name),
            "player_tag": ctypes.addressof(self.player_tag),
            "marker": ctypes.addressof(self.marker),
            "scan_min": scan_min,
            "scan_max": scan_max,
            "slow_min": slow_min,
            "slow_max": slow_min + ctypes.sizeof(self.slow_scan_buffer) - 1,
        }

    def execute(self, command: str) -> tuple[dict[str, Any], bool]:
        """Execute one line-oriented command and return its JSON response."""
        words = command.strip().split()
        if not words:
            return {"ok": False, "error": "empty command"}, False
        action = words[0].casefold()
        if action == "damage" and len(words) == 1:
            self.health[0] = max(0, self.health[0] - 27)
            return {"ok": True, "health": self.health[0]}, False
        if action == "heal" and len(words) == 1:
            self.health[0] += 15
            return {"ok": True, "health": self.health[0]}, False
        if action == "set" and len(words) == 3 and words[1].casefold() == "health":
            try:
                self.health[0] = int(words[2], 0)
            except ValueError:
                return {"ok": False, "error": "health must be an integer"}, False
            return {"ok": True, "health": self.health[0]}, False
        if action == "get" and len(words) == 2 and words[1].casefold() == "health":
            return {"ok": True, "health": self.health[0]}, False
        if action == "quit" and len(words) == 1:
            return {"ok": True, "event": "bye"}, True
        return {"ok": False, "error": f"unknown command: {command.strip()}"}, False


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def main() -> int:
    """Serve deterministic stdin commands until quit or EOF."""
    state = TargetState()
    _emit(state.manifest())
    for line in sys.stdin:
        response, should_quit = state.execute(line)
        _emit(response)
        if should_quit:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
