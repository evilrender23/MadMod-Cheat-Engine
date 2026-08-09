"""Win32 global hotkeys and foreground-process gating for the overlay."""

from __future__ import annotations

import ctypes
import sys
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from PySide6.QtCore import QAbstractNativeEventFilter, QByteArray

WM_HOTKEY = 0x0312
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
VK_PAUSE = 0x13
VK_OEM_5 = 0xDC
HOTKEY_OVERLAY_PAUSE = 0x4D50
HOTKEY_OVERLAY_DEGREE = 0x4D51
OVERLAY_HOTKEY_IDS = frozenset({HOTKEY_OVERLAY_PAUSE, HOTKEY_OVERLAY_DEGREE})


class GlobalHotkeys:
    """Register both overlay shortcuts and inspect native WM_HOTKEY messages."""

    def __init__(self, user32: Any | None = None) -> None:
        if user32 is not None:
            self._user32 = user32
        elif sys.platform == "win32":
            self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        else:
            self._user32 = None
        self._window_handle = 0
        self._registered: set[int] = set()

    @property
    def registered_ids(self) -> frozenset[int]:
        return frozenset(self._registered)

    def register(self, window_handle: int) -> tuple[str, ...]:
        """Register Pause and Ctrl+Shift+º; return labels that could not be registered."""
        self.unregister()
        if self._user32 is None or window_handle <= 0:
            return ("Pause", "Ctrl+Shift+º")
        self._window_handle = window_handle
        degree_key = int(self._user32.VkKeyScanW("º")) & 0xFF
        if degree_key == 0xFF:
            degree_key = VK_OEM_5
        requested = (
            (HOTKEY_OVERLAY_PAUSE, MOD_NOREPEAT, VK_PAUSE, "Pause"),
            (
                HOTKEY_OVERLAY_DEGREE,
                MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
                degree_key,
                "Ctrl+Shift+º",
            ),
        )
        failed: list[str] = []
        for hotkey_id, modifiers, virtual_key, label in requested:
            registered = bool(
                self._user32.RegisterHotKey(
                    wintypes.HWND(window_handle),
                    hotkey_id,
                    modifiers,
                    virtual_key,
                )
            )
            if registered:
                self._registered.add(hotkey_id)
            else:
                failed.append(label)
        return tuple(failed)

    def unregister(self) -> None:
        """Release every hotkey owned by the current main-window handle."""
        if self._user32 is not None and self._window_handle:
            for hotkey_id in tuple(self._registered):
                self._user32.UnregisterHotKey(
                    wintypes.HWND(self._window_handle),
                    hotkey_id,
                )
        self._registered.clear()
        self._window_handle = 0

    def event_hotkey_id(self, message_pointer: Any) -> int | None:
        """Return a registered overlay id for a native Qt message pointer."""
        address = int(message_pointer) if message_pointer is not None else 0
        if not address:
            return None
        message = ctypes.cast(address, ctypes.POINTER(wintypes.MSG)).contents
        hotkey_id = int(message.wParam)
        if int(message.message) != WM_HOTKEY or hotkey_id not in self._registered:
            return None
        return hotkey_id

    def foreground_pid(self) -> int | None:
        """Return the PID that owns the current foreground window."""
        if self._user32 is None:
            return None
        window = self._user32.GetForegroundWindow()
        if not window:
            return None
        pid = wintypes.DWORD()
        self._user32.GetWindowThreadProcessId(window, ctypes.byref(pid))
        return int(pid.value) if pid.value else None


class HotkeyEventFilter(QAbstractNativeEventFilter):
    """Dispatch registered WM_HOTKEY events before Qt swallows them."""

    def __init__(self, hotkeys: GlobalHotkeys, on_activated: Callable[[], None]) -> None:
        super().__init__()
        self._hotkeys = hotkeys
        self._on_activated = on_activated

    def nativeEventFilter(
        self,
        event_type: QByteArray | bytes | bytearray | memoryview,
        message: int,
    ) -> tuple[bool, int]:
        del event_type
        if self._hotkeys.event_hotkey_id(message) is None:
            return False, 0
        self._on_activated()
        return True, 0
