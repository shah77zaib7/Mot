"""One global shortcut (RegisterHotKey) that shows or hides the Mot window.

No new dependency: plain ctypes. The shortcut is registered against a
message-only window owned by a small pump thread, so Settings > General can
change it from any thread and get a yes/no answer straight back.

`Win32` is the whole Windows surface; tests hand `Hotkey` a fake with the
same methods and never register a real hotkey.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes
from typing import Any, Callable

log = logging.getLogger("mot")

DEFAULT_COMBO = "ctrl+alt+m"

WM_HOTKEY = 0x0312
PM_NOREMOVE = 0x0000
HOTKEY_ID = 1
HWND_MESSAGE = -3

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "windows": MOD_WIN,
}
_MOD_ORDER = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"),
              (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))


def _keys() -> dict[str, tuple[int, str]]:
    table: dict[str, tuple[int, str]] = {}
    for letter in "abcdefghijklmnopqrstuvwxyz":
        table[letter] = (ord(letter.upper()), letter.upper())
    for digit in "0123456789":
        table[digit] = (ord(digit), digit)
    for number in range(1, 25):
        table[f"f{number}"] = (0x70 + number - 1, f"F{number}")
    named = (
        ("space", "Space", 0x20), ("tab", "Tab", 0x09),
        ("esc", "Esc", 0x1B), ("escape", "Esc", 0x1B),
        ("enter", "Enter", 0x0D), ("return", "Enter", 0x0D),
        ("backspace", "Backspace", 0x08), ("insert", "Insert", 0x2D),
        ("delete", "Delete", 0x2E), ("home", "Home", 0x24),
        ("end", "End", 0x23), ("pageup", "PageUp", 0x21),
        ("pagedown", "PageDown", 0x22), ("up", "Up", 0x26),
        ("down", "Down", 0x28), ("left", "Left", 0x25),
        ("right", "Right", 0x27),
    )
    for token, label, vk in named:
        table[token] = (vk, label)
    return table


_KEYS = _keys()
_KEY_LABEL: dict[int, str] = {}
for _token, (_vk, _label) in _KEYS.items():
    _KEY_LABEL.setdefault(_vk, _label)


class BadHotkey(ValueError):
    """A shortcut Mot cannot use, worded for the Settings panel."""


def parse(combo: str) -> tuple[int, int]:
    """'ctrl+alt+m' -> (modifiers, virtual key). Raises BadHotkey."""
    text = str(combo or "").strip().lower()
    if not text:
        raise BadHotkey("Type a shortcut, for example Ctrl+Alt+M.")
    parts = [part for part in text.replace(" ", "").split("+") if part]
    mods = 0
    key = ""
    for part in parts:
        if part in _MODIFIERS:
            mods |= _MODIFIERS[part]
        elif key:
            raise BadHotkey(
                f'A shortcut is one key plus modifiers - "{combo}" has more than one key.')
        else:
            key = part
    if not key:
        raise BadHotkey("Add a key too, for example Ctrl+Alt+M.")
    if key not in _KEYS:
        raise BadHotkey(
            f'"{key}" is not a key Mot can use. Try a letter, a number or F1-F12.')
    if not mods:
        # A bare key would be swallowed from every other program.
        raise BadHotkey(
            "Add a modifier too, for example Ctrl+Alt+M - a key on its own "
            "would be taken away from every other app.")
    return mods, _KEYS[key][0]


def label(combo: str) -> str:
    """'ctrl+alt+m' -> 'Ctrl+Alt+M'."""
    mods, vk = parse(combo)
    names = [name for bit, name in _MOD_ORDER if mods & bit]
    names.append(_KEY_LABEL[vk])
    return "+".join(names)


def _taken(combo: str) -> str:
    try:
        pretty = label(combo)
    except ValueError:
        pretty = str(combo)
    return f'"{pretty}" is already used by another program. Pick a different shortcut.'


class Win32:
    """The Windows surface. Tests substitute an object with these methods."""

    def __init__(self) -> None:
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        msg = ctypes.POINTER(wintypes.MSG)
        self._user32.PeekMessageW.argtypes = [
            msg, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint]
        self._user32.PeekMessageW.restype = ctypes.c_int
        self._user32.GetMessageW.argtypes = [
            msg, ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
        self._user32.GetMessageW.restype = ctypes.c_int
        self._user32.TranslateMessage.argtypes = [msg]
        self._user32.DispatchMessageW.argtypes = [msg]
        self._user32.RegisterHotKey.argtypes = [
            ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
        self._user32.RegisterHotKey.restype = ctypes.c_int
        self._user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
        self._user32.UnregisterHotKey.restype = ctypes.c_int
        self._user32.PostThreadMessageW.argtypes = [
            ctypes.c_ulong, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.PostThreadMessageW.restype = ctypes.c_int
        self._user32.CreateWindowExW.argtypes = [
            ctypes.c_ulong, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self._user32.CreateWindowExW.restype = ctypes.c_void_p
        self._user32.DestroyWindow.argtypes = [ctypes.c_void_p]
        self._kernel32.GetCurrentThreadId.restype = ctypes.c_ulong
        self._kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
        self._kernel32.GetModuleHandleW.restype = ctypes.c_void_p

    def prepare(self) -> int:
        """Create this thread's message queue and report its id."""
        peeked = wintypes.MSG()
        self._user32.PeekMessageW(ctypes.byref(peeked), None, 0, 0, PM_NOREMOVE)
        return int(self._kernel32.GetCurrentThreadId())

    def create_window(self) -> int:
        hwnd = self._user32.CreateWindowExW(
            0, "STATIC", "Mot hotkey", 0, 0, 0, 0, 0,
            HWND_MESSAGE, None, self._kernel32.GetModuleHandleW(None), None)
        if not hwnd:
            raise OSError(ctypes.get_last_error(), "CreateWindowExW failed")
        return int(hwnd)

    def destroy_window(self, hwnd: int) -> None:
        if hwnd:
            self._user32.DestroyWindow(hwnd)

    def register(self, hwnd: int, combo: str) -> bool:
        mods, vk = parse(combo)
        return bool(self._user32.RegisterHotKey(hwnd, HOTKEY_ID, mods, vk))

    def unregister(self, hwnd: int) -> bool:
        if not hwnd:
            return True
        return bool(self._user32.UnregisterHotKey(hwnd, HOTKEY_ID))

    def post_quit(self, thread_id: int) -> None:
        if thread_id:
            self._user32.PostThreadMessageW(thread_id, 0x0012, 0, 0)  # WM_QUIT

    def pump(self, hwnd: int, on_hotkey: Callable[[], None]) -> None:
        """Block until post_quit(): this is the whole hotkey thread."""
        msg = wintypes.MSG()
        while True:
            result = self._user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result <= 0:  # WM_QUIT (0) or an error (-1)
                return
            if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                on_hotkey()
            self._user32.TranslateMessage(ctypes.byref(msg))
            self._user32.DispatchMessageW(ctypes.byref(msg))


class Hotkey:
    """The shortcut, its thread and its last error."""

    def __init__(self, api: Any | None = None) -> None:
        self._api = api
        self._combo: str = DEFAULT_COMBO
        self._on_press: Callable[[], None] | None = None
        self._error: str | None = None
        self._hwnd = 0
        self._tid = 0
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ---------------------------------------------------------
    def start(self, combo: str, on_press: Callable[[], None]) -> bool:
        """Open the message pump and register `combo`. False = it is taken."""
        try:
            parse(combo)
        except ValueError:
            log.warning("saved shortcut %r is not usable - using %s",
                        combo, DEFAULT_COMBO)
            combo = DEFAULT_COMBO
        self._combo = combo
        self._on_press = on_press
        self._error = None
        self._ready.clear()
        self._thread = threading.Thread(target=self._loop, name="mot-hotkey",
                                        daemon=True)
        self._thread.start()
        if not self._ready.wait(10.0):
            self._error = "Mot's keyboard shortcut could not be started."
            log.warning("the hotkey thread never came up")
            return False
        return self._error is None

    def _loop(self) -> None:
        """The whole shortcut thread. Whatever happens, `start()` must wake."""
        try:
            self._work()
        except Exception:  # noqa: BLE001 - no shortcut beats no app
            log.warning("the global shortcut could not start", exc_info=True)
            self._error = "Mot's keyboard shortcut could not be registered."
            self._hwnd = 0
            self._tid = 0
        finally:
            self._ready.set()

    def _work(self) -> None:
        if self._api is None:
            self._api = Win32()
        api = self._api
        self._tid = api.prepare()
        self._hwnd = api.create_window()
        try:
            if api.register(self._hwnd, self._combo):
                log.info("hotkey ready: %s", label(self._combo))
            else:
                self._error = _taken(self._combo)
                log.warning("hotkey %s is taken by another program", self._combo)
        except Exception:  # noqa: BLE001
            log.warning("the global shortcut could not register %s", self._combo,
                        exc_info=True)
            self._error = "Mot's keyboard shortcut could not be registered."
        # Registration is decided: start() and set() may now talk to us.
        self._ready.set()
        try:
            api.pump(self._hwnd, self._press)
        finally:
            hwnd = self._hwnd
            try:
                api.unregister(hwnd)
                api.destroy_window(hwnd)
            finally:
                self._hwnd = 0
                self._tid = 0

    def _press(self) -> None:
        if self._on_press is None:
            return
        # Off the pump thread: showing/hiding the window talks to the GUI thread.
        threading.Thread(target=self._on_press, name="mot-hotkey-fire",
                         daemon=True).start()

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is None:
            return
        api = self._api
        if api is not None:
            try:
                if self._hwnd:
                    api.unregister(self._hwnd)
                api.post_quit(self._tid)
            except Exception:  # noqa: BLE001
                pass
        if thread is not threading.current_thread():
            thread.join(timeout=3.0)
        self._hwnd = 0
        self._tid = 0
        self._ready.clear()

    # -- changing it from Settings ----------------------------------------
    def set(self, combo: str) -> tuple[bool, str | None]:
        """Register `combo`, keeping the old one when Windows refuses."""
        parse(combo)
        if self._thread is None:
            self._combo = combo  # not running: remembered for the next start
            return True, None
        if not self._ready.is_set() or not self._hwnd:
            self._combo = combo  # the pump failed earlier: still just a setting
            return True, None
        api = self._api
        old = self._combo
        api.unregister(self._hwnd)
        if api.register(self._hwnd, combo):
            self._combo, self._error = combo, None
            return True, None
        if old:
            api.register(self._hwnd, old)  # keep the working shortcut working
        self._error = _taken(combo)
        return False, self._error

    def status(self) -> dict[str, Any]:
        combo = self._combo or DEFAULT_COMBO
        try:
            pretty = label(combo)
        except ValueError:
            pretty = combo
        return {
            "combo": combo,
            "label": pretty,
            "active": self._thread is not None and self._error is None,
            "error": self._error,
        }


_default = Hotkey()


def start(combo: str, on_press: Callable[[], None]) -> bool:
    return _default.start(combo, on_press)


def apply(combo: str) -> tuple[bool, str | None]:
    """Validate `combo`, then register it when the shortcut service is up."""
    try:
        parse(combo)
    except ValueError as exc:
        return False, str(exc)
    return _default.set(combo)


def stop() -> None:
    _default.stop()


def status() -> dict[str, Any]:
    return _default.status()


def reset(instance: Hotkey | None = None) -> None:
    """Swap the process-wide shortcut (tests)."""
    global _default
    _default = instance or Hotkey()
