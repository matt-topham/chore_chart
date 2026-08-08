from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS chores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT 'General',
    frequency TEXT NOT NULL,
    preferred_day TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    first_due TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    source_row INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(task, area)
);

CREATE TABLE IF NOT EXISTS completions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chore_id INTEGER NOT NULL,
    completed_at TEXT NOT NULL,
    completed_date TEXT NOT NULL,
    completed_by TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (chore_id) REFERENCES chores(id) ON DELETE CASCADE,
    UNIQUE(chore_id, completed_date)
);

CREATE TABLE IF NOT EXISTS groceries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    quantity TEXT NOT NULL DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    due_date TEXT NOT NULL,
    icon TEXT NOT NULL DEFAULT '🔔',
    notes TEXT NOT NULL DEFAULT '',
    completed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_completions_chore_date
ON completions(chore_id, completed_date DESC);

CREATE INDEX IF NOT EXISTS idx_reminders_due_date
ON reminders(completed, due_date);
"""


@contextmanager
def connect_db(database_path: str | Path) -> Iterator[sqlite3.Connection]:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    try:
        yield connection
    finally:
        connection.close()


def ensure_database(database_path: str | Path) -> None:
    with connect_db(database_path) as db:
        db.executescript(SCHEMA)
        db.commit()
