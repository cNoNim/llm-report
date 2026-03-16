"""SQLite reader for the Codex state database."""

from __future__ import annotations

import glob
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class StateReadError(RuntimeError):
    """Raised when the state database cannot be read safely."""


def find_state_db(codex_home: Path) -> Path | None:
    """Find the highest-version state_*.sqlite file in CODEX_HOME."""
    pattern = str(codex_home / "state_*.sqlite")
    matches = glob.glob(pattern)
    if not matches:
        return None
    return max((Path(match) for match in matches), key=_state_db_sort_key)


def _state_db_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    _, _, suffix = stem.partition("_")
    try:
        return (int(suffix), path.name)
    except ValueError:
        return (-1, path.name)


def _epoch_to_iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def read_threads(db_path: Path) -> list[dict[str, Any]]:
    """Read all threads from the state database."""
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, title, created_at, updated_at, source,
                   model_provider, tokens_used, rollout_path,
                   agent_nickname, agent_role
            FROM threads
            ORDER BY created_at
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise StateReadError(f"Failed to read threads from {db_path}: {exc}") from exc
    finally:
        conn.close()

    return [_row_to_thread(row) for row in rows]


def _row_to_thread(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "created_at": _epoch_to_iso(row["created_at"]),
        "updated_at": _epoch_to_iso(row["updated_at"]),
        "source": row["source"],
        "model_provider": row["model_provider"],
        "tokens_used": row["tokens_used"],
        "rollout_path": row["rollout_path"],
        "agent_nickname": row["agent_nickname"],
        "agent_role": row["agent_role"],
    }
