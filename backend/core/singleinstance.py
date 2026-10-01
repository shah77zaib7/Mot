"""One Mot at a time: a named mutex, plus a wake-up event for the winner.

The first process creates both objects. A second launch finds the mutex
already there, pokes the event — the running instance shows its window (or
brings it back from the tray) — and then exits silently.

Everything goes through `Win32`; tests hand `Instance` an object with the same
methods, so no test ever creates a real kernel object.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from typing import Any, Callable

log = logging.getLogger("mot")

MUTEX_NAME = "Local\\MotSingleInstance"
EVENT_NAME = "Local\\MotWakeUp"

ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0x00000000
WAIT_TIMEOUT = 0x00000102
POLL_MS = 250  # how often the listener wakes up to notice it is stopping


class Win32:
    """The handful of kernel32 calls this module needs."""

    def __init__(self) -> None:
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        self._k32.CreateMutexW.restype = ctypes.c_void_p
        self._k32.CreateEventW.argtypes = [
            ctypes.c_void_p, ctypes.c_bool, ctypes.c_bool, ctypes.c_wchar_p]
        self._k32.CreateEventW.restype = ctypes.c_void_p
        self._k32.OpenEventW.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_wchar_p]
        self._k32.OpenEventW.restype = ctypes.c_void_p
        self._k32.SetEvent.argtypes = [ctypes.c_void_p]
        self._k32.SetEvent.restype = ctypes.c_bool
        self._k32.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._k32.WaitForSingleObject.restype = ctypes.c_ulong
        self._k32.CloseHandle.argtypes = [ctypes.c_void_p]
        self._k32.CloseHandle.restype = ctypes.c_bool

    def create_mutex(self, name: str) -> tuple[int, bool]:
        """(handle, already_existed). The handle keeps the mutex alive."""
        handle = self._k32.CreateMutexW(None, False, name)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
        return int(handle), ctypes.get_last_error() == ERROR_ALREADY_EXISTS

    def create_event(self, name: str) -> int:
        """An auto-reset event: one poke wakes one wait."""
        handle = self._k32.CreateEventW(None, False, False, name)
        if not handle:
            raise OSError(ctypes.get_last_error(), "CreateEventW failed")
        return int(handle)

    def open_event(self, name: str) -> int:
        handle = self._k32.OpenEventW(0x0002, False, name)  # EVENT_MODIFY_STATE
        return int(handle) if handle else 0

    def set_event(self, handle: int) -> bool:
        return bool(self._k32.SetEvent(handle))

    def wait(self, handle: int, ms: int) -> int:
        return int(self._k32.WaitForSingleObject(handle, ms))

    def close(self, handle: int) -> None:
        if handle:
            self._k32.CloseHandle(handle)


class Instance:
    """One process's claim on being "the only Mot"."""

    def __init__(self, api: Any | None = None) -> None:
        self._api = api
        self._mutex = 0
        self._event = 0
        self._owns = False
        self._stopping = threading.Event()
        self._thread: threading.Thread | None = None

    # -- plumbing ----------------------------------------------------------
    def _win(self) -> Any:
        if self._api is None:
            self._api = Win32()
        return self._api

    # -- the gate ----------------------------------------------------------
    def acquire(self, wake: bool = True) -> bool:
        """Claim the single Mot.

        True  -> this process owns it, carry on.
        False -> another Mot is already running; it is asked to come to the
        front (unless `wake` is False, which is what `--background` uses).
        """
        if self._owns:
            return True
        win = self._win()
        handle, existed = win.create_mutex(MUTEX_NAME)
        if existed:
            win.close(handle)
            if wake:
                self.notify()
            return False
        self._mutex = handle
        self._event = win.create_event(EVENT_NAME)
        self._owns = True
        return True

    def notify(self) -> bool:
        """Poke the running instance so it shows its window."""
        win = self._win()
        handle = win.open_event(EVENT_NAME)
        if not handle:
            return False
        try:
            return bool(win.set_event(handle))
        finally:
            win.close(handle)

    def start_listener(self, on_activate: Callable[[], None]) -> bool:
        """Wait for `notify()` on a daemon thread. Owner only."""
        if not self._owns or not self._event:
            return False

        def loop() -> None:
            while not self._stopping.is_set():
                got = self._win().wait(self._event, POLL_MS)
                if self._stopping.is_set():
                    break
                if got != WAIT_OBJECT_0:
                    continue
                try:
                    on_activate()
                except Exception:  # noqa: BLE001 - a failed wake must not kill the loop
                    log.warning("a second launch could not show the window",
                                exc_info=True)

        self._thread = threading.Thread(target=loop, name="mot-wake", daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        """Release the mutex and the listener (clean shutdown, tests)."""
        self._stopping.set()
        win = self._api
        if win is not None and self._event:
            try:
                win.set_event(self._event)  # wake the listener so it can exit
            except Exception:  # noqa: BLE001
                pass
        thread, self._thread = self._thread, None
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        if win is not None:
            for handle in (self._event, self._mutex):
                try:
                    win.close(handle)
                except Exception:  # noqa: BLE001
                    pass
        self._event = 0
        self._mutex = 0
        self._owns = False
        self._stopping.clear()


_default = Instance()


def acquire(wake: bool = True) -> bool:
    return _default.acquire(wake)


def notify() -> bool:
    return _default.notify()


def start_listener(on_activate: Callable[[], None]) -> bool:
    return _default.start_listener(on_activate)


def stop() -> None:
    _default.stop()
