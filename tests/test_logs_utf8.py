"""Phase 6: mot.log is UTF-8 — Urdu, roman-Urdu and emoji all survive it."""
from __future__ import annotations

import logging
from contextlib import contextmanager

NATIVE = "Urdu: سلام دنیا! یہ ایک ٹیسٹ ہے۔"
ROMAN = "Roman-Urdu: kya haal hai boss, sab theek?"
EMOJI = "Emoji: 🚀 ✅ 🎉 👍🏽"


@contextmanager
def mot_log(tmp_path, monkeypatch):
    """Run the app's real setup_logging() against a throwaway folder.

    pytest keeps its own handler on the root logger during the call phase, so
    it has to be moved aside for `setup_logging` (which no-ops on a logger that
    already has handlers) and put straight back afterwards.
    """
    from backend import main
    from backend.core import config

    monkeypatch.setattr(config, "LOG_DIR", tmp_path)
    root = logging.getLogger()
    others = list(root.handlers)
    level = root.level
    for handler in others:
        root.removeHandler(handler)
    main.setup_logging(quiet=True)
    ours = list(root.handlers)
    for handler in others:
        root.addHandler(handler)
    try:
        yield tmp_path / "mot.log"
    finally:
        for handler in root.handlers:
            handler.flush()
        for handler in ours:
            root.removeHandler(handler)
            handler.close()
        root.setLevel(level)


def test_mot_log_is_written_as_utf8(tmp_path, monkeypatch):
    with mot_log(tmp_path, monkeypatch) as path:
        logging.getLogger("mot").info("%s | %s | %s", NATIVE, ROMAN, EMOJI)

        raw = path.read_bytes()
        text = raw.decode("utf-8")  # strict: mojibake would raise right here

        assert "سلام دنیا!" in text
        assert "kya haal hai boss, sab theek?" in text
        assert "🚀 ✅ 🎉 👍🏽" in text
        assert "\ufffd" not in text  # no replacement characters
        assert not raw.startswith(b"\xff\xfe") and not raw.startswith(b"\xfe\xff")


def test_a_later_line_still_reads_back_cleanly(tmp_path, monkeypatch):
    log = logging.getLogger("mot")

    with mot_log(tmp_path, monkeypatch) as path:
        log.info("first line, plain ascii")
        log.info("switched models: میڈل ایسٹ -> medel east 🕌")
        log.warning("cooldown %s", "گولڈ 🥇")

        lines = path.read_text(encoding="utf-8").splitlines()

    assert any("میڈل ایسٹ -> medel east 🕌" in line for line in lines)
    assert any("cooldown گولڈ 🥇" in line for line in lines)
    assert all("\ufffd" not in line for line in lines)
