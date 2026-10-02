"""SQLite storage for chats and messages (data/mot.db)."""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .config import DATA_DIR

DB_PATH: Path = DATA_DIR / "mot.db"
_LOCK = threading.Lock()
_CONN: sqlite3.Connection | None = None


def close() -> None:
    """Shut the connection so SQLite checkpoints the WAL and releases the file."""
    global _CONN
    with _LOCK:
        if _CONN is None:
            return
        conn, _CONN = _CONN, None
        try:
            conn.close()
        except Exception:  # noqa: BLE001 - closing must never fail a shutdown
            logging.getLogger("mot").warning("could not close the database",
                                             exc_info=True)


def _conn() -> sqlite3.Connection:
    global _CONN
    if _CONN is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _CONN = sqlite3.connect(DB_PATH, check_same_thread=False)
        _CONN.row_factory = sqlite3.Row
        _CONN.execute("PRAGMA journal_mode=WAL")
        _CONN.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                profile TEXT,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        _CONN.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                profile TEXT,
                created_at REAL NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
            """
        )
        _CONN.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id)"
        )
        columns = {row[1] for row in _CONN.execute("PRAGMA table_info(messages)")}
        if "actions" not in columns:  # Phase 2: action cards live on the message
            _CONN.execute("ALTER TABLE messages ADD COLUMN actions TEXT")
        _CONN.commit()
    return _CONN


def _new_id() -> str:
    return uuid.uuid4().hex


def list_chats() -> list[dict[str, Any]]:
    with _LOCK:
        rows = _conn().execute(
            "SELECT id, title, profile, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def create_chat(profile: str | None = None, title: str = "New chat") -> dict[str, Any]:
    chat = {
        "id": _new_id(),
        "title": title[:80],
        "profile": profile,
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    with _LOCK:
        conn = _conn()
        conn.execute(
            "INSERT INTO chats (id, title, profile, created_at, updated_at) VALUES (?,?,?,?,?)",
            (chat["id"], chat["title"], profile, chat["created_at"], chat["updated_at"]),
        )
        conn.commit()
    return chat


def get_chat(chat_id: str) -> dict[str, Any] | None:
    with _LOCK:
        row = _conn().execute("SELECT * FROM chats WHERE id=?", (chat_id,)).fetchone()
    return dict(row) if row else None


def touch_chat(chat_id: str, title: str | None = None, profile: str | None = None) -> None:
    sets, args = ["updated_at=?"], [time.time()]
    if title:
        sets.append("title=?")
        args.append(title[:80])
    if profile:
        sets.append("profile=?")
        args.append(profile)
    args.append(chat_id)
    with _LOCK:
        conn = _conn()
        conn.execute(f"UPDATE chats SET {', '.join(sets)} WHERE id=?", args)
        conn.commit()


def delete_chat(chat_id: str) -> bool:
    with _LOCK:
        conn = _conn()
        conn.execute("DELETE FROM messages WHERE chat_id=?", (chat_id,))
        cur = conn.execute("DELETE FROM chats WHERE id=?", (chat_id,))
        conn.commit()
    return cur.rowcount > 0


def drop_last_assistant(chat_id: str) -> None:
    """Remove the trailing assistant reply (used by Regenerate)."""
    with _LOCK:
        conn = _conn()
        conn.execute(
            "DELETE FROM messages WHERE id = ("
            "SELECT id FROM messages WHERE chat_id=? AND role='assistant' "
            "ORDER BY created_at DESC LIMIT 1)",
            (chat_id,),
        )
        conn.commit()


def get_messages(chat_id: str) -> list[dict[str, Any]]:
    with _LOCK:
        rows = _conn().execute(
            "SELECT id, chat_id, role, content, profile, actions, created_at FROM messages "
            "WHERE chat_id=? ORDER BY created_at ASC",
            (chat_id,),
        ).fetchall()
    return [_with_actions(dict(r)) for r in rows]


def _with_actions(message: dict[str, Any]) -> dict[str, Any]:
    raw = message.get("actions")
    if isinstance(raw, str) and raw:
        try:
            message["actions"] = json.loads(raw)
        except json.JSONDecodeError:
            message["actions"] = []
    else:
        message.pop("actions", None)
    return message


def add_message(
    chat_id: str,
    role: str,
    content: str,
    profile: str | None = None,
    actions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = json.dumps(actions, ensure_ascii=False) if actions else None
    message = {
        "id": _new_id(),
        "chat_id": chat_id,
        "role": role,
        "content": content,
        "profile": profile,
        "actions": actions,
        "created_at": time.time(),
    }
    with _LOCK:
        conn = _conn()
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, profile, actions, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (message["id"], chat_id, role, content, profile, payload,
             message["created_at"]),
        )
        conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (message["created_at"], chat_id))
        conn.commit()
    if not actions:
        message.pop("actions", None)
    return message


def _scan_actions(action_id: str | None) -> tuple[Any, list[dict[str, Any]]] | None:
    """Find (message row id, actions) containing `action_id`."""
    conn = _conn()
    rows = conn.execute(
        "SELECT id, actions FROM messages WHERE actions IS NOT NULL"
    ).fetchall()
    for row in rows:
        try:
            actions = json.loads(row["actions"] or "[]")
        except json.JSONDecodeError:
            continue
        if not isinstance(actions, list):
            continue
        if action_id is None or any(a.get("id") == action_id for a in actions):
            return row["id"], actions
    return None


def find_action(action_id: str) -> dict[str, Any] | None:
    with _LOCK:
        found = _scan_actions(action_id)
        if found is None:
            return None
        _row_id, actions = found
        return next((a for a in actions if a.get("id") == action_id), None)


def update_action(action_id: str | None, patch: dict[str, Any]) -> dict[str, Any] | None:
    """Merge `patch` into a stored action and return the updated copy."""
    if not action_id:
        return None
    with _LOCK:
        found = _scan_actions(action_id)
        if found is None:
            return None
        row_id, actions = found
        target = next((a for a in actions if a.get("id") == action_id), None)
        if target is None:
            return None
        target.update(patch)
        conn = _conn()
        conn.execute(
            "UPDATE messages SET actions=? WHERE id=?",
            (json.dumps(actions, ensure_ascii=False), row_id),
        )
        conn.commit()
        return dict(target)


def title_from(text: str) -> str:
    clean = " ".join(text.split())
    return clean[:60] if clean else "New chat"
