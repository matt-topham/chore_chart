from __future__ import annotations

import json
import mimetypes
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from .db import connect_db, ensure_database
from .importer import import_workbook
from .scheduler import next_due_date


class ChoreHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class,
        *,
        database_path: Path,
        workbook_path: Path,
        base_dir: Path,
        timezone_name: str,
        upcoming_days: int,
    ):
        super().__init__(server_address, handler_class)
        self.database_path = database_path
        self.workbook_path = workbook_path
        self.base_dir = base_dir
        self.timezone_name = timezone_name
        self.upcoming_days = upcoming_days


class ChoreRequestHandler(BaseHTTPRequestHandler):
    server: ChoreHTTPServer

    def log_message(self, format_string: str, *args) -> None:
        print(f"[{self.log_date_time_string()}] {format_string % args}")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self._send_file(self.server.base_dir / "chore_app/templates/index.html", "text/html")
        if parsed.path == "/history":
            return self._send_file(self.server.base_dir / "chore_app/templates/history.html", "text/html")
        if parsed.path.startswith("/static/"):
            relative = parsed.path.removeprefix("/static/")
            static_root = (self.server.base_dir / "chore_app/static").resolve()
            target = (static_root / relative).resolve()
            if static_root not in target.parents:
                return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return self._send_file(target)
        if parsed.path == "/api/chores":
            return self._get_chores(parse_qs(parsed.query))
        if parsed.path == "/api/history":
            return self._get_history(parse_qs(parsed.query))
        if parsed.path == "/health":
            return self._json({"ok": True})
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        complete_match = re.fullmatch(r"/api/chores/(\d+)/complete", parsed.path)
        if complete_match:
            return self._complete_chore(int(complete_match.group(1)))
        if parsed.path == "/api/admin/reimport":
            return self._reimport()
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        undo_match = re.fullmatch(r"/api/completions/(\d+)", parsed.path)
        if undo_match:
            return self._undo_completion(int(undo_match.group(1)))
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _local_now(self) -> datetime:
        return datetime.now(ZoneInfo(self.server.timezone_name))

    def _read_json(self) -> dict:
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    def _json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.is_file():
            return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        body = path.read_bytes()
        guessed = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", f"{guessed}; charset=utf-8" if guessed.startswith("text/") else guessed)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _last_completion(self, db: sqlite3.Connection, chore_id: int) -> dict | None:
        row = db.execute(
            """
            SELECT id, completed_at, completed_date, completed_by
            FROM completions
            WHERE chore_id = ?
            ORDER BY completed_date DESC, completed_at DESC
            LIMIT 1
            """,
            (chore_id,),
        ).fetchone()
        return dict(row) if row else None

    def _serialize_chore(self, db: sqlite3.Connection, row: sqlite3.Row, today: date) -> dict:
        chore = dict(row)
        completion = self._last_completion(db, chore["id"])
        last_completed = date.fromisoformat(completion["completed_date"]) if completion else None
        due = next_due_date(chore, last_completed)
        return {
            **chore,
            "last_completed": last_completed.isoformat() if last_completed else None,
            "last_completion_id": completion["id"] if completion else None,
            "next_due": due.isoformat(),
            "days_overdue": max(0, (today - due).days),
            "is_due": due <= today,
            "is_completed_today": last_completed == today,
        }

    def _get_chores(self, query: dict[str, list[str]]) -> None:
        today_text = query.get("date", [None])[0]
        try:
            today = date.fromisoformat(today_text) if today_text else self._local_now().date()
        except ValueError:
            return self._json({"error": "date must use YYYY-MM-DD"}, HTTPStatus.BAD_REQUEST)

        with connect_db(self.server.database_path) as db:
            rows = db.execute(
                "SELECT * FROM chores WHERE active = 1 ORDER BY area, task"
            ).fetchall()
            chores = [self._serialize_chore(db, row, today) for row in rows]

        due = sorted(
            [item for item in chores if item["is_due"]],
            key=lambda item: (item["next_due"], item["area"], item["task"]),
        )
        completed_today = sorted(
            [item for item in chores if item["is_completed_today"]],
            key=lambda item: (item["area"], item["task"]),
        )
        upcoming_limit = today + timedelta(days=self.server.upcoming_days)
        upcoming = sorted(
            [
                item for item in chores
                if not item["is_due"]
                and not item["is_completed_today"]
                and date.fromisoformat(item["next_due"]) <= upcoming_limit
            ],
            key=lambda item: (item["next_due"], item["area"], item["task"]),
        )
        return self._json(
            {
                "date": today.isoformat(),
                "due": due,
                "completed_today": completed_today,
                "upcoming": upcoming,
                "counts": {
                    "due": len(due),
                    "completed": len(completed_today),
                    "upcoming": len(upcoming),
                },
            }
        )

    def _complete_chore(self, chore_id: int) -> None:
        payload = self._read_json()
        completed_by = str(payload.get("completed_by", "")).strip()[:80]
        now = self._local_now()
        completed_at = now.astimezone(timezone.utc).isoformat()
        completed_date = now.date().isoformat()

        with connect_db(self.server.database_path) as db:
            chore = db.execute(
                "SELECT id FROM chores WHERE id = ? AND active = 1", (chore_id,)
            ).fetchone()
            if not chore:
                return self._json({"error": "Chore not found"}, HTTPStatus.NOT_FOUND)
            try:
                cursor = db.execute(
                    """
                    INSERT INTO completions
                        (chore_id, completed_at, completed_date, completed_by)
                    VALUES (?, ?, ?, ?)
                    """,
                    (chore_id, completed_at, completed_date, completed_by),
                )
                db.commit()
                completion_id = cursor.lastrowid
            except sqlite3.IntegrityError:
                existing = db.execute(
                    "SELECT id FROM completions WHERE chore_id = ? AND completed_date = ?",
                    (chore_id, completed_date),
                ).fetchone()
                return self._json(
                    {"ok": True, "already_completed": True, "completion_id": existing["id"]}
                )
        return self._json({"ok": True, "completion_id": completion_id})

    def _undo_completion(self, completion_id: int) -> None:
        with connect_db(self.server.database_path) as db:
            row = db.execute(
                "SELECT id FROM completions WHERE id = ?", (completion_id,)
            ).fetchone()
            if not row:
                return self._json({"error": "Completion not found"}, HTTPStatus.NOT_FOUND)
            db.execute("DELETE FROM completions WHERE id = ?", (completion_id,))
            db.commit()
        return self._json({"ok": True})

    def _get_history(self, query: dict[str, list[str]]) -> None:
        try:
            limit = int(query.get("limit", ["100"])[0])
        except ValueError:
            limit = 100
        limit = min(max(limit, 1), 500)
        with connect_db(self.server.database_path) as db:
            rows = db.execute(
                """
                SELECT c.task, c.area, c.frequency,
                       x.id AS completion_id, x.completed_at, x.completed_date, x.completed_by
                FROM completions x
                JOIN chores c ON c.id = x.chore_id
                ORDER BY x.completed_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return self._json({"history": [dict(row) for row in rows]})

    def _reimport(self) -> None:
        result = import_workbook(
            self.server.workbook_path,
            self.server.database_path,
            replace=False,
            imported_on=self._local_now().date(),
        )
        return self._json({"ok": True, **result})


def initialize_data(database_path: Path, workbook_path: Path, timezone_name: str) -> dict[str, int] | None:
    ensure_database(database_path)
    with connect_db(database_path) as db:
        count = db.execute("SELECT COUNT(*) FROM chores").fetchone()[0]
    if count == 0 and workbook_path.exists():
        local_date = datetime.now(ZoneInfo(timezone_name)).date()
        return import_workbook(
            workbook_path,
            database_path,
            replace=False,
            imported_on=local_date,
        )
    return None


def build_server(
    host: str,
    port: int,
    *,
    database_path: Path,
    workbook_path: Path,
    base_dir: Path,
    timezone_name: str = "America/Denver",
    upcoming_days: int = 7,
) -> ChoreHTTPServer:
    initialize_data(database_path, workbook_path, timezone_name)
    return ChoreHTTPServer(
        (host, port),
        ChoreRequestHandler,
        database_path=database_path,
        workbook_path=workbook_path,
        base_dir=base_dir,
        timezone_name=timezone_name,
        upcoming_days=upcoming_days,
    )
