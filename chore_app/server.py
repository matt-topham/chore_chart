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
from .integrations import get_calendar, get_weather
from .scheduler import next_due_date


class ChoreHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, server_address, handler_class, *, database_path: Path, workbook_path: Path, base_dir: Path, timezone_name: str, upcoming_days: int):
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
        routes = {
            "/": "dashboard.html",
            "/tasks": "index.html",
            "/history": "history.html",
            "/groceries": "groceries.html",
        }
        if parsed.path in routes:
            return self._send_file(self.server.base_dir / "chore_app/templates" / routes[parsed.path], "text/html")
        if parsed.path.startswith("/static/"):
            relative = parsed.path.removeprefix("/static/")
            static_root = (self.server.base_dir / "chore_app/static").resolve()
            target = (static_root / relative).resolve()
            if static_root not in target.parents:
                return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return self._send_file(target)
        if parsed.path == "/api/chores": return self._get_chores(parse_qs(parsed.query))
        if parsed.path == "/api/history": return self._get_history(parse_qs(parsed.query))
        if parsed.path == "/api/dashboard": return self._get_dashboard()
        if parsed.path == "/api/weather": return self._json(get_weather(self.server.timezone_name))
        if parsed.path == "/api/calendar": return self._json(get_calendar(self.server.timezone_name))
        if parsed.path == "/api/groceries": return self._get_groceries()
        if parsed.path == "/api/reminders": return self._get_reminders()
        if parsed.path == "/api/notes": return self._get_notes()
        if parsed.path == "/health": return self._json({"ok": True})
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        match = re.fullmatch(r"/api/chores/(\d+)/complete", parsed.path)
        if match: return self._complete_chore(int(match.group(1)))
        match = re.fullmatch(r"/api/groceries/(\d+)/toggle", parsed.path)
        if match: return self._toggle_grocery(int(match.group(1)))
        match = re.fullmatch(r"/api/reminders/(\d+)/complete", parsed.path)
        if match: return self._complete_reminder(int(match.group(1)))
        if parsed.path == "/api/groceries": return self._add_grocery()
        if parsed.path == "/api/reminders": return self._add_reminder()
        if parsed.path == "/api/notes": return self._add_note()
        if parsed.path == "/api/admin/reimport": return self._reimport()
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        match = re.fullmatch(r"/api/completions/(\d+)", parsed.path)
        if match: return self._undo_completion(int(match.group(1)))
        match = re.fullmatch(r"/api/groceries/(\d+)", parsed.path)
        if match: return self._delete_row("groceries", int(match.group(1)))
        match = re.fullmatch(r"/api/reminders/(\d+)", parsed.path)
        if match: return self._delete_row("reminders", int(match.group(1)))
        match = re.fullmatch(r"/api/notes/(\d+)", parsed.path)
        if match: return self._delete_row("notes", int(match.group(1)))
        return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

    def _local_now(self) -> datetime:
        return datetime.now(ZoneInfo(self.server.timezone_name))

    def _read_json(self) -> dict:
        try: length = int(self.headers.get("Content-Length", "0"))
        except ValueError: length = 0
        if length <= 0: return {}
        try: return json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError): return {}

    def _json(self, payload, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str | None = None) -> None:
        if not path.is_file(): return self._json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        body = path.read_bytes(); guessed = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", f"{guessed}; charset=utf-8" if guessed.startswith("text/") else guessed)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers(); self.wfile.write(body)

    def _last_completion(self, db: sqlite3.Connection, chore_id: int):
        row = db.execute("SELECT id, completed_at, completed_date, completed_by FROM completions WHERE chore_id=? ORDER BY completed_date DESC, completed_at DESC LIMIT 1", (chore_id,)).fetchone()
        return dict(row) if row else None

    def _serialize_chore(self, db, row, today: date) -> dict:
        chore = dict(row); completion = self._last_completion(db, chore["id"])
        last_completed = date.fromisoformat(completion["completed_date"]) if completion else None
        due = next_due_date(chore, last_completed)
        return {**chore, "last_completed": last_completed.isoformat() if last_completed else None, "last_completion_id": completion["id"] if completion else None, "next_due": due.isoformat(), "days_overdue": max(0, (today-due).days), "is_due": due <= today, "is_completed_today": last_completed == today}

    def _chore_payload(self, today: date) -> dict:
        with connect_db(self.server.database_path) as db:
            rows = db.execute("SELECT * FROM chores WHERE active=1 ORDER BY area,task").fetchall()
            chores = [self._serialize_chore(db, row, today) for row in rows]
        due = sorted([x for x in chores if x["is_due"]], key=lambda x:(x["next_due"],x["area"],x["task"]))
        completed = sorted([x for x in chores if x["is_completed_today"]], key=lambda x:(x["area"],x["task"]))
        limit = today + timedelta(days=self.server.upcoming_days)
        upcoming = sorted([x for x in chores if not x["is_due"] and not x["is_completed_today"] and date.fromisoformat(x["next_due"]) <= limit], key=lambda x:(x["next_due"],x["area"],x["task"]))
        return {"date":today.isoformat(),"due":due,"completed_today":completed,"upcoming":upcoming,"counts":{"due":len(due),"completed":len(completed),"upcoming":len(upcoming)}}

    def _get_chores(self, query) -> None:
        text = query.get("date", [None])[0]
        try: today = date.fromisoformat(text) if text else self._local_now().date()
        except ValueError: return self._json({"error":"date must use YYYY-MM-DD"}, HTTPStatus.BAD_REQUEST)
        return self._json(self._chore_payload(today))

    def _get_dashboard(self) -> None:
        today = self._local_now().date(); chores = self._chore_payload(today)
        with connect_db(self.server.database_path) as db:
            groceries = [dict(r) for r in db.execute("SELECT * FROM groceries WHERE completed=0 ORDER BY id DESC LIMIT 8").fetchall()]
            reminders = [dict(r) for r in db.execute("SELECT * FROM reminders WHERE completed=0 ORDER BY due_date,id LIMIT 8").fetchall()]
            notes = [dict(r) for r in db.execute("SELECT * FROM notes ORDER BY id DESC LIMIT 4").fetchall()]
        self._json({"chores":chores,"groceries":groceries,"reminders":reminders,"notes":notes,"weather":get_weather(self.server.timezone_name),"calendar":get_calendar(self.server.timezone_name)})

    def _complete_chore(self, chore_id: int) -> None:
        payload=self._read_json(); completed_by=str(payload.get("completed_by","")).strip()[:80]; now=self._local_now(); completed_at=now.astimezone(timezone.utc).isoformat(); completed_date=now.date().isoformat()
        with connect_db(self.server.database_path) as db:
            if not db.execute("SELECT id FROM chores WHERE id=? AND active=1",(chore_id,)).fetchone(): return self._json({"error":"Chore not found"},HTTPStatus.NOT_FOUND)
            try:
                cursor=db.execute("INSERT INTO completions(chore_id,completed_at,completed_date,completed_by) VALUES(?,?,?,?)",(chore_id,completed_at,completed_date,completed_by)); db.commit(); cid=cursor.lastrowid
            except sqlite3.IntegrityError:
                cid=db.execute("SELECT id FROM completions WHERE chore_id=? AND completed_date=?",(chore_id,completed_date)).fetchone()["id"]
                return self._json({"ok":True,"already_completed":True,"completion_id":cid})
        self._json({"ok":True,"completion_id":cid})

    def _undo_completion(self, completion_id:int)->None:
        with connect_db(self.server.database_path) as db:
            if not db.execute("SELECT id FROM completions WHERE id=?",(completion_id,)).fetchone(): return self._json({"error":"Completion not found"},HTTPStatus.NOT_FOUND)
            db.execute("DELETE FROM completions WHERE id=?",(completion_id,)); db.commit()
        self._json({"ok":True})

    def _get_history(self, query)->None:
        try: limit=int(query.get("limit",["100"])[0])
        except ValueError: limit=100
        limit=min(max(limit,1),500)
        with connect_db(self.server.database_path) as db:
            rows=db.execute("SELECT c.task,c.area,c.frequency,x.id AS completion_id,x.completed_at,x.completed_date,x.completed_by FROM completions x JOIN chores c ON c.id=x.chore_id ORDER BY x.completed_at DESC LIMIT ?",(limit,)).fetchall()
        self._json({"history":[dict(r) for r in rows]})

    def _get_groceries(self)->None:
        with connect_db(self.server.database_path) as db: rows=db.execute("SELECT * FROM groceries ORDER BY completed,id DESC").fetchall()
        self._json({"groceries":[dict(r) for r in rows]})

    def _add_grocery(self)->None:
        p=self._read_json(); item=str(p.get("item","")).strip()[:120]
        if not item: return self._json({"error":"Item is required"},HTTPStatus.BAD_REQUEST)
        category=str(p.get("category","Other")).strip()[:50] or "Other"; quantity=str(p.get("quantity","")).strip()[:40]
        with connect_db(self.server.database_path) as db: cur=db.execute("INSERT INTO groceries(item,category,quantity) VALUES(?,?,?)",(item,category,quantity)); db.commit()
        self._json({"ok":True,"id":cur.lastrowid},HTTPStatus.CREATED)

    def _toggle_grocery(self,row_id:int)->None:
        now=self._local_now().astimezone(timezone.utc).isoformat()
        with connect_db(self.server.database_path) as db:
            row=db.execute("SELECT completed FROM groceries WHERE id=?",(row_id,)).fetchone()
            if not row:return self._json({"error":"Not found"},HTTPStatus.NOT_FOUND)
            completed=0 if row["completed"] else 1; db.execute("UPDATE groceries SET completed=?,completed_at=? WHERE id=?",(completed,now if completed else None,row_id)); db.commit()
        self._json({"ok":True,"completed":bool(completed)})

    def _get_reminders(self)->None:
        with connect_db(self.server.database_path) as db: rows=db.execute("SELECT * FROM reminders WHERE completed=0 ORDER BY due_date,id").fetchall()
        self._json({"reminders":[dict(r) for r in rows]})

    def _add_reminder(self)->None:
        p=self._read_json(); title=str(p.get("title","")).strip()[:140]; due=str(p.get("due_date","")).strip()
        try: date.fromisoformat(due)
        except ValueError: return self._json({"error":"Valid due_date is required"},HTTPStatus.BAD_REQUEST)
        if not title:return self._json({"error":"Title is required"},HTTPStatus.BAD_REQUEST)
        icon=str(p.get("icon","🔔"))[:8]; notes=str(p.get("notes","")).strip()[:300]
        with connect_db(self.server.database_path) as db: cur=db.execute("INSERT INTO reminders(title,due_date,icon,notes) VALUES(?,?,?,?)",(title,due,icon,notes)); db.commit()
        self._json({"ok":True,"id":cur.lastrowid},HTTPStatus.CREATED)

    def _complete_reminder(self,row_id:int)->None:
        now=self._local_now().astimezone(timezone.utc).isoformat()
        with connect_db(self.server.database_path) as db:
            cur=db.execute("UPDATE reminders SET completed=1,completed_at=? WHERE id=?",(now,row_id)); db.commit()
            if not cur.rowcount:return self._json({"error":"Not found"},HTTPStatus.NOT_FOUND)
        self._json({"ok":True})

    def _get_notes(self)->None:
        with connect_db(self.server.database_path) as db: rows=db.execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
        self._json({"notes":[dict(r) for r in rows]})

    def _add_note(self)->None:
        body=str(self._read_json().get("body","")).strip()[:500]
        if not body:return self._json({"error":"Note is required"},HTTPStatus.BAD_REQUEST)
        with connect_db(self.server.database_path) as db: cur=db.execute("INSERT INTO notes(body) VALUES(?)",(body,)); db.commit()
        self._json({"ok":True,"id":cur.lastrowid},HTTPStatus.CREATED)

    def _delete_row(self,table:str,row_id:int)->None:
        with connect_db(self.server.database_path) as db: cur=db.execute(f"DELETE FROM {table} WHERE id=?",(row_id,)); db.commit()
        self._json({"ok":bool(cur.rowcount)})

    def _reimport(self)->None:
        result=import_workbook(self.server.workbook_path,self.server.database_path,replace=False,imported_on=self._local_now().date()); self._json({"ok":True,**result})


def initialize_data(database_path:Path,workbook_path:Path,timezone_name:str):
    ensure_database(database_path)
    with connect_db(database_path) as db: count=db.execute("SELECT COUNT(*) FROM chores").fetchone()[0]
    if count==0 and workbook_path.exists(): return import_workbook(workbook_path,database_path,replace=False,imported_on=datetime.now(ZoneInfo(timezone_name)).date())
    return None


def build_server(host:str,port:int,*,database_path:Path,workbook_path:Path,base_dir:Path,timezone_name:str="America/Denver",upcoming_days:int=7)->ChoreHTTPServer:
    initialize_data(database_path,workbook_path,timezone_name)
    return ChoreHTTPServer((host,port),ChoreRequestHandler,database_path=database_path,workbook_path=workbook_path,base_dir=base_dir,timezone_name=timezone_name,upcoming_days=upcoming_days)
