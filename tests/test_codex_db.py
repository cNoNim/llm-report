"""Tests for Codex state DB discovery and low-level DB errors."""

import sqlite3

import pytest

from llm_report.codex_db import StateReadError, find_state_db, read_threads


def test_find_state_db_prefers_highest_numeric_version(tmp_path):
    (tmp_path / "state_9.sqlite").write_text("")
    (tmp_path / "state_10.sqlite").write_text("")
    (tmp_path / "state_11.sqlite").write_text("")

    db_path = find_state_db(tmp_path)

    assert db_path == tmp_path / "state_11.sqlite"


def test_read_threads_raises_state_read_error_for_invalid_schema(tmp_path):
    db_path = tmp_path / "state_5.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE not_threads (id TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    with pytest.raises(StateReadError, match="Failed to read threads"):
        read_threads(db_path)
