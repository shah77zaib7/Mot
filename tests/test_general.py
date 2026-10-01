"""Phase 5A: single instance, tray, shortcut, auto-start, close behaviour.

Every Windows surface (kernel32, winreg, pystray, RegisterHotKey) is faked
here, so no test ever changes a real Windows setting or creates a real icon.
"""
from __future__ import annotations

import inspect
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.core import singleinstance

ROOT = Path(__file__).resolve().parents[1]


def wait_until(fn, timeout: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        time.sleep(0.01)
    return fn()


# --- single instance --------------------------------------------------------

class FakeKernel:
    """kernel32 in 40 lines: one mutex, named auto-reset events, fake handles."""

    def __init__(self) -> None:
        self._next = 1
        self._handles: dict[int, tuple[str, str]] = {}
        self.events: dict[str, threading.Event] = {}
        self.mutex_exists = False
        self.opened: list[str] = []

    def _handle(self, kind: str, name: str) -> int:
        handle = self._next
        self._next += 1
        self._handles[handle] = (kind, name)
        return handle

    def create_mutex(self, name: str) -> tuple[int, bool]:
        existed = self.mutex_exists
        self.mutex_exists = True
        return self._handle("mutex", name), existed

    def create_event(self, name: str) -> int:
        event = self.events.setdefault(name, threading.Event())
        event.clear()
        return self._handle("event", name)

    def open_event(self, name: str) -> int:
        if name not in self.events:
            return 0
        self.opened.append(name)
        return self._handle("event", name)

    def _event(self, handle: int) -> threading.Event | None:
        found = self._handles.get(handle)
        return self.events.get(found[1]) if found and found[0] == "event" else None

    def set_event(self, handle: int) -> bool:
        event = self._event(handle)
        if event is None:
            return False
        event.set()
        return True

    def wait(self, handle: int, ms: int) -> int:
        event = self._event(handle)
        if event is None:
            return 0x102
        if not event.wait(ms / 1000.0):
            return 0x102
        event.clear()  # auto-reset: one poke wakes exactly one wait
        return 0

    def close(self, handle: int) -> None:
        self._handles.pop(handle, None)


def test_a_second_launch_wakes_the_first_one_and_steps_aside():
    kernel = FakeKernel()
    first = singleinstance.Instance(api=kernel)
    second = singleinstance.Instance(api=kernel)
    woken: list[int] = []

    assert first.acquire() is True
    assert first.start_listener(lambda: woken.append(1)) is True
    assert second.acquire() is False  # it never becomes the owner

    assert wait_until(lambda: woken == [1])
    first.stop()
    assert first._owns is False


def test_a_background_launch_does_not_pop_the_window():
    kernel = FakeKernel()
    first = singleinstance.Instance(api=kernel)
    second = singleinstance.Instance(api=kernel)
    woken: list[int] = []

    first.acquire()
    first.start_listener(lambda: woken.append(1))
    assert second.acquire(wake=False) is False

    time.sleep(0.35)  # long enough for at least one listener poll
    assert woken == []
    first.stop()


def test_a_listener_refuses_to_work_without_the_mutex():
    listener = singleinstance.Instance(api=FakeKernel())

    assert listener.start_listener(lambda: None) is False
    listener.stop()


# --- auto-start -------------------------------------------------------------

class FakeKey:
    def __init__(self, path: str) -> None:
        self.path = path

    def __enter__(self) -> "FakeKey":
        return self

    def __exit__(self, *exc) -> bool:
        return False


class FakeWinreg:
    """HKCU, two operations, nothing else in the registry."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}
        self.created: list[str] = []
        self.deleted: list[str] = []

    def OpenKey(self, parent, path, reserved=0, access=0):  # noqa: N802 - winreg naming
        return FakeKey(path)

    def CreateKey(self, parent, path):  # noqa: N802 - winreg naming
        self.created.append(path)
        return FakeKey(path)

    def QueryValueEx(self, key, name):  # noqa: N802 - winreg naming
        if (key.path, name) not in self.values:
            raise FileNotFoundError(name)
        return self.values[(key.path, name)], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        self.values[(key.path, name)] = value

    def DeleteValue(self, key, name):  # noqa: N802 - winreg naming
        if (key.path, name) not in self.values:
            raise FileNotFoundError(name)
        del self.values[(key.path, name)]
        self.deleted.append(name)


@pytest.fixture
def winreg(monkeypatch):
    from backend.core import autostart

    store = FakeWinreg()
    monkeypatch.setattr(autostart, "_reg", lambda: store)
    return store


def test_auto_start_adds_exactly_one_run_key_and_takes_it_away(winreg):
    from backend.core import autostart

    assert autostart.enabled() is False

    autostart.set_enabled(True)
    value = winreg.values[(autostart.KEY_PATH, autostart.VALUE_NAME)]
    assert "pythonw" in value.lower()
    assert str(ROOT / "run.pyw") in value
    assert value.rstrip().endswith("--background")
    assert set(winreg.values) == {(autostart.KEY_PATH, autostart.VALUE_NAME)}
    assert set(winreg.created) == {autostart.KEY_PATH}

    autostart.set_enabled(False)
    assert autostart.enabled() is False
    assert winreg.values == {}
    assert set(winreg.deleted) == {autostart.VALUE_NAME}


def test_turning_auto_start_off_twice_is_harmless(winreg):
    from backend.core import autostart

    autostart.set_enabled(False)
    autostart.set_enabled(False)

    assert autostart.enabled() is False
    assert winreg.deleted == []  # nothing to delete: no error, no writes


def test_the_startup_command_never_opens_a_console():
    from backend.core import autostart

    command = autostart.command()

    assert command.startswith('"')
    assert "pythonw.exe" in command
    assert "run.pyw" in command
    assert "--background" in command


# --- the global shortcut ----------------------------------------------------

class FakeHotkeyApi:
    """The Win32 surface of hotkey.Win32: a window, a slot, a pump."""

    def __init__(self, taken: tuple[str, ...] = ()) -> None:
        self.taken = set(taken)
        self.current: str | None = None
        self.registered: list[str] = []
        self._quit = threading.Event()
        self.window = 0

    def prepare(self) -> int:
        return 42

    def create_window(self) -> int:
        self.window = 7
        return self.window

    def destroy_window(self, hwnd: int) -> None:
        self.window = 0

    def register(self, hwnd: int, combo: str) -> bool:
        self.registered.append(combo)
        if combo in self.taken:
            return False
        self.current = combo
        return True

    def unregister(self, hwnd: int) -> bool:
        self.current = None
        return True

    def post_quit(self, thread_id: int) -> None:
        self._quit.set()

    def pump(self, hwnd: int, on_hotkey) -> None:
        self._quit.wait(5.0)


def test_a_shortcut_that_is_taken_keeps_the_old_one_working():
    from backend.core import hotkey

    api = FakeHotkeyApi(taken=("ctrl+alt+m",))
    service = hotkey.Hotkey(api)

    assert service.start("ctrl+alt+m", lambda: None) is False
    assert "already used" in (service.status()["error"] or "")

    assert service.set("ctrl+shift+j") == (True, None)
    assert service.status()["combo"] == "ctrl+shift+j"
    assert service.status()["error"] is None
    assert api.current == "ctrl+shift+j"

    ok, message = service.set("ctrl+alt+m")  # still taken by the other program
    assert ok is False and message and "already used" in message
    assert service.status()["combo"] == "ctrl+shift+j"  # the old one came back
    assert api.current == "ctrl+shift+j"

    service.stop()


def test_a_shortcut_is_one_key_plus_at_least_one_modifier():
    from backend.core import hotkey

    assert hotkey.parse("ctrl+alt+m") == (
        hotkey.MOD_CONTROL | hotkey.MOD_ALT, ord("M"))
    assert hotkey.label("ctrl+alt+m") == "Ctrl+Alt+M"
    assert hotkey.label("Shift + F5") == "Shift+F5"
    assert hotkey.label("win+space") == "Win+Space"

    for bad in ("", "m", "ctrl+alt", "ctrl+alt+nope", "ctrl+m+n"):
        with pytest.raises(ValueError):
            hotkey.parse(bad)


def test_a_saved_shortcut_that_is_garbage_falls_back_to_the_default():
    from backend.core import hotkey

    api = FakeHotkeyApi()
    service = hotkey.Hotkey(api)

    assert service.start("nonsense", lambda: None) is True
    assert api.current == hotkey.DEFAULT_COMBO
    service.stop()


def test_the_shortcut_callback_runs_off_the_pump_thread():
    """WM_HOTKEY must never block on showing/hiding the window."""
    from backend.core import hotkey

    started = threading.Event()
    release = threading.Event()

    def slow() -> None:
        started.set()
        release.wait(2.0)

    service = hotkey.Hotkey(FakeHotkeyApi())
    service.start("ctrl+alt+m", slow)

    began = time.perf_counter()
    service._press()  # what the pump thread does on WM_HOTKEY
    elapsed = time.perf_counter() - began

    assert elapsed < 0.5  # it came straight back; `slow` is still running
    assert started.wait(1.0)
    release.set()
    service.stop()


# --- the tray ---------------------------------------------------------------

class FakeMenuItem:
    def __init__(self, text, action, default=False, **_kw) -> None:
        self.text = text
        self.action = action
        self.default = default


class FakeMenu:
    SEPARATOR = "---"

    def __init__(self, *items) -> None:
        self.items = items


class FakeIcon:
    def __init__(self, name, image, title, menu) -> None:
        self.name, self.image, self.title, self.menu = name, image, title, menu
        self.stopped = False
        self.notices: list[str] = []
        self._loop = threading.Event()

    def run(self) -> None:
        self._loop.wait(5.0)

    def stop(self) -> None:
        self.stopped = True
        self._loop.set()

    def notify(self, message, title=None) -> None:
        self.notices.append(message)


class FakePystray:
    MenuItem = FakeMenuItem
    Menu = FakeMenu
    Icon = FakeIcon


@pytest.fixture
def tray(monkeypatch):
    from backend.core import tray as tray_module

    monkeypatch.setattr(tray_module, "_pystray", lambda: FakePystray)
    monkeypatch.setattr(tray_module, "_image", lambda: "an-image")
    yield tray_module
    tray_module.stop()


def _menu_items(icon) -> dict[str, FakeMenuItem]:
    return {item.text: item for item in icon.menu.items if isinstance(item, FakeMenuItem)}


def test_the_tray_menu_opens_refreshes_and_quits(tray):
    opened, refreshed, quitted = [], [], []

    assert tray.start(lambda: opened.append(1),
                      lambda: refreshed.append(1),
                      lambda: quitted.append(1)) is True
    assert wait_until(lambda: tray.running())

    icon = tray._icon
    items = _menu_items(icon)
    assert list(items) == ["Open Mot", "Refresh news now", "Quit Mot"]
    assert isinstance(icon.menu.items[2], str)  # a separator sits between them

    # left-click on the icon activates the default item
    defaults = [i for i in icon.menu.items
                if isinstance(i, FakeMenuItem) and i.default]
    assert [i.text for i in defaults] == ["Open Mot"]

    defaults[0].action(icon)
    items["Refresh news now"].action(icon)
    items["Quit Mot"].action(icon)
    assert opened == [1] and refreshed == [1] and quitted == [1]

    tray.stop()
    assert icon.stopped is True
    assert tray.running() is False


def test_a_missing_tray_never_stops_the_app(tray, monkeypatch):
    def boom() -> None:
        raise ImportError("pystray is not installed")

    monkeypatch.setattr(tray, "_pystray", boom)

    assert tray.start(lambda: None, lambda: None, lambda: None) is False
    assert tray.running() is False


# --- close behaviour --------------------------------------------------------

class FakeEvent:
    def __init__(self) -> None:
        self.handlers: list = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self

    def fire(self, *args, **kwargs) -> None:
        """pywebview only passes the window to handlers that ask for it."""
        for handler in list(self.handlers):
            if len(inspect.signature(handler).parameters) == 0:
                handler()
            else:
                handler(*args, **kwargs)


class FakeWindow:
    def __init__(self) -> None:
        self.events = SimpleNamespace(shown=FakeEvent(), minimized=FakeEvent(),
                                      restored=FakeEvent())
        self.calls: list[str] = []

    def show(self) -> None:
        self.calls.append("show")

    def hide(self) -> None:
        self.calls.append("hide")

    def restore(self) -> None:
        self.calls.append("restore")

    def destroy(self) -> None:
        self.calls.append("destroy")


@pytest.fixture
def windowctl(monkeypatch, tmp_path):
    from backend.core import config, windowctl as ctl

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    boxes: list[str] = []
    monkeypatch.setattr(ctl, "message_box", boxes.append)
    ctl.detach()
    yield ctl, boxes
    ctl.detach()


def test_the_x_goes_to_the_tray_and_says_so_exactly_once(windowctl):
    ctl, boxes = windowctl
    window = FakeWindow()
    ctl.attach(window)

    assert ctl.on_closing(window) is False  # the close is cancelled
    assert wait_until(lambda: len(boxes) == 1)  # hide, then the one-time notice
    assert ctl.is_hidden() is True
    assert "notification area" in boxes[0]

    # closing again: still hidden, but the notice never repeats
    assert ctl.on_closing(window) is False
    assert wait_until(lambda: window.calls.count("hide") == 2)
    time.sleep(0.2)  # long enough that a second notice would have landed
    assert len(boxes) == 1


def test_when_the_user_asks_for_quit_the_x_really_quits(windowctl):
    from backend.core import config

    ctl, _boxes = windowctl
    config.set_general({"close_to_tray": False})
    window = FakeWindow()
    ctl.attach(window)

    assert ctl.on_closing(window) is True  # not cancelled


def test_quit_mot_closes_even_when_the_x_goes_to_the_tray(windowctl):
    ctl, _boxes = windowctl
    window = FakeWindow()
    ctl.attach(window)

    ctl.quit()
    assert wait_until(lambda: "destroy" in window.calls)
    assert ctl.on_closing(window) is True  # quitting is never cancelled again


def test_the_hotkey_shows_a_hidden_window_and_hides_a_visible_one(windowctl):
    ctl, _boxes = windowctl
    window = FakeWindow()
    ctl.attach(window, hidden=True)

    ctl.toggle()
    assert "show" in window.calls
    assert ctl.is_hidden() is False

    ctl.toggle()
    assert wait_until(lambda: window.calls[-1] == "hide")
    assert ctl.is_hidden() is True


def test_the_hotkey_brings_back_a_minimised_window(windowctl):
    ctl, _boxes = windowctl
    window = FakeWindow()
    ctl.attach(window)
    window.events.minimized.fire(window)

    ctl.toggle()

    assert window.calls == ["restore", "show"]
    assert ctl.is_hidden() is False


# --- Settings > General API -------------------------------------------------

@pytest.fixture
def winreg_store() -> FakeWinreg:
    return FakeWinreg()


@pytest.fixture
def client(tmp_path, monkeypatch, winreg_store):
    from fastapi.testclient import TestClient

    from backend.core import apps, autostart, config, db, feeds, hotkey, routines
    from backend.main import create_app

    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(autostart, "_reg", lambda: winreg_store)
    monkeypatch.setattr(apps, "APPS_PATH", tmp_path / "apps.json")
    monkeypatch.setattr(routines, "ROUTINES_PATH", tmp_path / "routines.json")
    monkeypatch.setattr(feeds, "FEEDS_PATH", tmp_path / "feeds.json")
    monkeypatch.setattr(apps, "rescan_if_stale", lambda: None)
    hotkey.reset()
    if db._CONN is not None:
        db._CONN.close()
        db._CONN = None
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "mot.db")

    with TestClient(create_app()) as test_client:
        yield test_client

    hotkey.reset()
    if db._CONN is not None:
        db._CONN.close()
        db._CONN = None


def test_general_starts_with_a_tray_close_a_default_shortcut_and_no_autostart(client):
    body = client.get("/api/general").json()

    assert body["close_to_tray"] is True
    assert body["hotkey"] == "ctrl+alt+m"
    assert body["hotkey_label"] == "Ctrl+Alt+M"
    assert body["autostart"] is False


def test_close_behaviour_round_trips(client):
    saved = client.put("/api/general", json={"close_to_tray": False}).json()

    assert saved["ok"] is True
    assert saved["close_to_tray"] is False
    assert client.get("/api/general").json()["close_to_tray"] is False


def test_an_unusable_shortcut_is_refused_and_the_old_one_kept(client):
    before = client.get("/api/general").json()

    refused = client.put("/api/general", json={"hotkey": "m"}).json()

    assert refused["ok"] is False
    assert refused["message"] and "modifier" in refused["message"]
    assert refused["hotkey"] == before["hotkey"] == "ctrl+alt+m"

    accepted = client.put("/api/general", json={"hotkey": "Ctrl+Shift+J"}).json()
    assert accepted["ok"] is True
    assert accepted["hotkey"] == "ctrl+shift+j"
    assert accepted["hotkey_label"] == "Ctrl+Shift+J"


def test_auto_start_is_untouched_when_the_registry_refuses(
        client, winreg_store, monkeypatch):
    from backend.core import autostart

    def refuse(on: bool) -> None:
        raise RuntimeError("Windows would not save the startup entry.")

    monkeypatch.setattr(autostart, "set_enabled", refuse)

    body = client.put("/api/general", json={"autostart": True}).json()

    assert body["ok"] is False
    assert "Windows would not save" in body["message"]
    assert body["autostart"] is False
    assert winreg_store.values == {}  # and nothing was written either way


def test_auto_start_flips_the_single_registry_entry(client, winreg_store):
    assert client.put("/api/general", json={"autostart": True}).json()["autostart"] is True
    assert len(winreg_store.values) == 1

    assert client.put("/api/general", json={"autostart": False}).json()["autostart"] is False
    assert winreg_store.values == {}


# --- startup stays light ----------------------------------------------------

def test_startup_never_imports_the_expensive_modules():
    """litellm costs ~10 s, pystray+PIL ~300 ms: none of them may load early."""
    code = (
        "import sys; sys.path.insert(0, %r); import backend.main; "
        "print([m for m in ('litellm', 'pystray', 'PIL') if m in sys.modules])"
        % str(ROOT)
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, timeout=120, cwd=str(ROOT))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
