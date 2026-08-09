"""Windows hotkey registration and native-message parsing contracts."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

import pytest

from mempilot.ui.hotkeys import (
    HOTKEY_OVERLAY_DEGREE,
    HOTKEY_OVERLAY_PAUSE,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MOD_SHIFT,
    VK_PAUSE,
    WM_HOTKEY,
    GlobalHotkeys,
)

pytestmark = pytest.mark.windows


class _FakeUser32:
    def __init__(self) -> None:
        self.registered: list[tuple[int, int, int, int]] = []
        self.unregistered: list[tuple[int, int]] = []

    def VkKeyScanW(self, character: str) -> int:
        assert character == "º"
        return 0xDC

    def RegisterHotKey(self, hwnd: Any, hotkey_id: int, modifiers: int, key: int) -> int:
        self.registered.append((int(hwnd.value), hotkey_id, modifiers, key))
        return 1

    def UnregisterHotKey(self, hwnd: Any, hotkey_id: int) -> int:
        self.unregistered.append((int(hwnd.value), hotkey_id))
        return 1

    def GetForegroundWindow(self) -> int:
        return 0

    def GetWindowThreadProcessId(self, window: int, pid: Any) -> int:
        del window, pid
        return 0


class _FalseyQtPointer:
    """Model Shiboken.VoidPtr, whose truth value is false when its size is zero."""

    def __init__(self, address: int) -> None:
        self._address = address

    def __int__(self) -> int:
        return self._address

    def __bool__(self) -> bool:
        return False


def test_registers_pause_and_spanish_degree_shortcut_and_releases_them() -> None:
    hotkeys = GlobalHotkeys()
    fake = _FakeUser32()
    hotkeys._user32 = fake

    assert hotkeys.register(1234) == ()
    assert fake.registered == [
        (1234, HOTKEY_OVERLAY_PAUSE, MOD_NOREPEAT, VK_PAUSE),
        (
            1234,
            HOTKEY_OVERLAY_DEGREE,
            MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
            0xDC,
        ),
    ]

    hotkeys.unregister()
    assert set(fake.unregistered) == {
        (1234, HOTKEY_OVERLAY_PAUSE),
        (1234, HOTKEY_OVERLAY_DEGREE),
    }


def test_native_hotkey_parser_rejects_other_messages() -> None:
    hotkeys = GlobalHotkeys()
    hotkeys._user32 = _FakeUser32()
    assert hotkeys.register(1234) == ()
    message = wintypes.MSG()
    message.message = WM_HOTKEY
    message.wParam = HOTKEY_OVERLAY_DEGREE
    pointer = _FalseyQtPointer(ctypes.addressof(message))
    assert hotkeys.event_hotkey_id(pointer) == HOTKEY_OVERLAY_DEGREE

    message.message = 0x0100
    assert hotkeys.event_hotkey_id(ctypes.addressof(message)) is None
