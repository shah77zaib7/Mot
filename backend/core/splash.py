"""A tiny native "Mot is starting..." window, up before anything heavy loads.

pywebview + WebView2 take seconds, and a double-click that does nothing for
three seconds looks broken. This is a plain Win32 popup drawn with ctypes —
no extra dependency, no second Python stack — created by `run.pyw` right
after the one-instance gate and destroyed when the real window appears.

It is best effort: if anything here fails, Mot carries on without a splash
and a warning goes to the log. The splash never blocks a launch.
"""
from __future__ import annotations

import ctypes
import logging
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger("mot")

CLASS_NAME = "MotSplashWindow"
TEXT = "Mot is starting..."

# window / style
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
WS_EX_TOOLWINDOW = 0x00000080  # no taskbar button
WS_EX_TOPMOST = 0x00000008
SW_SHOW = 5
WM_PAINT = 0x000F
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001
IDC_ARROW = 32512
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
DI_NORMAL = 0x0003
TRANSPARENT_BG = 2
DT_CENTER = 0x00000001
DT_SINGLELINE = 0x00000020
DT_VCENTER = 0x00000004
FW_NORMAL = 400

# The app's own palette: #0c0d10 background, #e7e8ea text (COLORREF = 0x00BBGGRR)
COLOR_BG = 0x00100D0C
COLOR_TEXT = 0x00EAE8E7

WIDTH, HEIGHT = 340, 140
ICON_SIZE = 56
TEXT_TOP = 92
TITLE_SIZE = -20  # negative = character height, so it scales with the DPI

# A window procedure returns LRESULT (a pointer-sized integer) — a plain
# c_long is 4 bytes even on x64 and was enough to break the hotkey once.
_LRESULT = ctypes.c_ssize_t
_PTR = ctypes.c_void_p

_WNDPROC = ctypes.WINFUNCTYPE(_LRESULT, wintypes.HWND, ctypes.c_uint,
                              wintypes.WPARAM, wintypes.LPARAM)


class _WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint),
        ("lpfnWndProc", _WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", _PTR),
        ("hIcon", _PTR),
        ("hCursor", _PTR),
        ("hbrBackground", _PTR),
        ("lpszMenuName", ctypes.c_wchar_p),
        ("lpszClassName", ctypes.c_wchar_p),
    ]


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", ctypes.c_uint),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# HMODULE is a 64-bit pointer: without a restype ctypes truncates it to int,
# and RegisterClassW/CreateWindowExW then get a garbage hInstance.
_kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]
_kernel32.GetModuleHandleW.restype = _PTR

_user32.DefWindowProcW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                   wintypes.WPARAM, wintypes.LPARAM]
_user32.DefWindowProcW.restype = _LRESULT
_user32.RegisterClassW.argtypes = [ctypes.POINTER(_WNDCLASSW)]
_user32.RegisterClassW.restype = ctypes.c_ushort
_user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, ctypes.c_wchar_p, ctypes.c_wchar_p, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, _PTR, _PTR, _PTR]
_user32.CreateWindowExW.restype = wintypes.HWND
_user32.DestroyWindow.argtypes = [wintypes.HWND]
_user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
_user32.UpdateWindow.argtypes = [wintypes.HWND]
_user32.SetForegroundWindow.argtypes = [wintypes.HWND]
_user32.PostMessageW.argtypes = [wintypes.HWND, ctypes.c_uint,
                                 wintypes.WPARAM, wintypes.LPARAM]
_user32.PostQuitMessage.argtypes = [ctypes.c_int]
_user32.GetMessageW.argtypes = [ctypes.POINTER(_MSG), wintypes.HWND,
                                ctypes.c_uint, ctypes.c_uint]
_user32.GetMessageW.restype = ctypes.c_int
_user32.TranslateMessage.argtypes = [ctypes.POINTER(_MSG)]
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(_MSG)]
_user32.DispatchMessageW.restype = _LRESULT
_user32.LoadCursorW.argtypes = [_PTR, _PTR]  # id = MAKEINTRESOURCE(32512)
_user32.LoadCursorW.restype = _PTR
_user32.LoadImageW.argtypes = [_PTR, ctypes.c_wchar_p, ctypes.c_uint,
                               ctypes.c_int, ctypes.c_int, ctypes.c_uint]
_user32.LoadImageW.restype = _PTR
_user32.DrawIconEx.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int,
                               _PTR, ctypes.c_int, ctypes.c_int,
                               ctypes.c_uint, _PTR, ctypes.c_uint]
_user32.DrawTextW.argtypes = [wintypes.HDC, ctypes.c_wchar_p, ctypes.c_int,
                              ctypes.POINTER(wintypes.RECT), ctypes.c_uint]
_user32.DrawTextW.restype = ctypes.c_int
_user32.GetDC.argtypes = [wintypes.HWND]
_user32.GetDC.restype = wintypes.HDC
_user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
_user32.GetSystemMetrics.argtypes = [ctypes.c_int]

_gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.DWORD]
_gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
_gdi32.CreateSolidBrush.argtypes = [wintypes.DWORD]
_gdi32.CreateSolidBrush.restype = _PTR
_gdi32.CreateFontW.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, ctypes.c_uint,
                               ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                               ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                               ctypes.c_uint, ctypes.c_wchar_p]
_gdi32.CreateFontW.restype = _PTR
_gdi32.SelectObject.argtypes = [wintypes.HDC, _PTR]
_gdi32.SelectObject.restype = _PTR

_hwnd: int | None = None
_thread: threading.Thread | None = None
_proc: Any = None  # the WNDPROC callback must stay referenced for Win32
_font: int | None = None
_brush: int | None = None
_icon: int | None = None
_registered = False


def _load_icon() -> int | None:
    icon_file: Path = paths.icon_path()
    if not icon_file.is_file():
        return None
    return _user32.LoadImageW(None, str(icon_file), IMAGE_ICON, 0, 0,
                              LR_LOADFROMFILE)


def _paint(hwnd: int) -> None:
    hdc = _user32.GetDC(hwnd)
    if not hdc:
        return
    try:
        if _icon:
            _user32.DrawIconEx(hdc, (WIDTH - ICON_SIZE) // 2, 18, _icon,
                               ICON_SIZE, ICON_SIZE, 0, None, DI_NORMAL)
        rect = wintypes.RECT(0, TEXT_TOP, WIDTH, HEIGHT - 6)
        old = _gdi32.SelectObject(hdc, _font) if _font else None
        _gdi32.SetBkMode(hdc, TRANSPARENT_BG)
        _gdi32.SetTextColor(hdc, COLOR_TEXT)
        _user32.DrawTextW(hdc, TEXT, -1, ctypes.byref(rect),
                          DT_CENTER | DT_SINGLELINE | DT_VCENTER)
        if old:
            _gdi32.SelectObject(hdc, old)
    finally:
        _user32.ReleaseDC(hwnd, hdc)


def _wndproc(hwnd: int, msg: int, wparam: Any, lparam: Any) -> int:
    if msg == WM_PAINT:
        _user32.DefWindowProcW(hwnd, msg, wparam, lparam)  # background brush
        try:
            _paint(hwnd)
        except Exception:  # noqa: BLE001 - a splash must never kill a launch
            log.warning("splash paint failed", exc_info=True)
        return 0
    if msg == WM_DESTROY:
        _user32.PostQuitMessage(0)  # or the message loop below never ends
        return 0
    return int(_user32.DefWindowProcW(hwnd, msg, wparam, lparam))


def _centre(width: int, height: int) -> tuple[int, int]:
    screen_w = _user32.GetSystemMetrics(0)
    screen_h = _user32.GetSystemMetrics(1)
    return max(0, (screen_w - width) // 2), max(0, (screen_h - height) // 2)


def _build(ready: threading.Event) -> None:
    """Runs on its own thread with its own message loop."""
    global _hwnd, _registered, _proc, _font, _brush, _icon
    try:
        hinstance = _kernel32.GetModuleHandleW(None)
        if not _registered:
            _proc = _WNDPROC(_wndproc)  # keep a reference: Win32 calls back
            _brush = _gdi32.CreateSolidBrush(COLOR_BG)
            _font = _gdi32.CreateFontW(TITLE_SIZE, 0, 0, 0, FW_NORMAL, 0, 0,
                                       0, 0, 0, 0, 0, 0, "Segoe UI")
            _icon = _load_icon()
            wc = _WNDCLASSW()
            wc.style = CS_HREDRAW | CS_VREDRAW
            wc.lpfnWndProc = _proc
            wc.hInstance = hinstance
            wc.hCursor = _user32.LoadCursorW(None, IDC_ARROW)
            wc.hbrBackground = _brush
            wc.lpszClassName = CLASS_NAME
            if not _user32.RegisterClassW(ctypes.byref(wc)):
                raise ctypes.WinError(ctypes.get_last_error())
            _registered = True

        x, y = _centre(WIDTH, HEIGHT)
        hwnd = _user32.CreateWindowExW(
            WS_EX_TOOLWINDOW | WS_EX_TOPMOST, CLASS_NAME, TEXT,
            WS_POPUP | WS_VISIBLE, x, y, WIDTH, HEIGHT,
            None, None, hinstance, None)
        if not hwnd:
            ready.set()
            return
        _hwnd = hwnd
        _user32.ShowWindow(hwnd, SW_SHOW)
        _user32.UpdateWindow(hwnd)
        _user32.SetForegroundWindow(hwnd)
        ready.set()

        msg = _MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
    except Exception:  # noqa: BLE001 - best effort, always wake the caller
        log.warning("splash could not open", exc_info=True)
        ready.set()


def show(started: float | None = None) -> bool:
    """Open the splash now. Returns True once it is on screen."""
    global _thread
    if _thread is not None:
        return _hwnd is not None
    ready = threading.Event()
    at = time.perf_counter()
    _thread = threading.Thread(target=_build, args=(ready,), daemon=True,
                               name="mot-splash")
    _thread.start()
    ready.wait(3.0)
    if _hwnd is None:
        _thread = None  # a failed attempt may be retried
        return False
    log.info("splash: on screen after %.0f ms",
             (time.perf_counter() - (started if started is not None else at))
             * 1000)
    return True


def close() -> None:
    """Destroy the splash (safe to call when there is none)."""
    global _hwnd, _thread
    hwnd, _hwnd = _hwnd, None
    if hwnd:
        try:
            _user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        except Exception:  # noqa: BLE001 - a dead window is not an error
            log.warning("splash could not close", exc_info=True)
    thread, _thread = _thread, None
    if thread is not None:
        thread.join(timeout=2.0)


def is_open() -> bool:
    return _hwnd is not None
