from __future__ import annotations

import json
from urllib import error, request


class DashboardClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _request(self, path: str, method: str = "GET", payload: dict | None = None) -> dict:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=8) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body).get("error", body)
            except json.JSONDecodeError:
                detail = body
            raise RuntimeError(f"Dashboard returned {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Could not reach dashboard: {exc.reason}") from exc

    def chores(self) -> dict:
        return self._request("/api/chores")

    def complete_chore(self, chore_id: int) -> dict:
        return self._request(f"/api/chores/{chore_id}/complete", "POST", {})

    def groceries(self) -> list[dict]:
        return self._request("/api/groceries").get("groceries", [])

    def add_grocery(self, item: str, category: str = "Other", quantity: str = "") -> dict:
        return self._request("/api/groceries", "POST", {"item": item, "category": category, "quantity": quantity})

    def add_reminder(self, title: str, due_date: str, notes: str = "") -> dict:
        return self._request("/api/reminders", "POST", {"title": title, "due_date": due_date, "notes": notes, "icon": "🔔"})

    def add_note(self, body: str) -> dict:
        return self._request("/api/notes", "POST", {"body": body})

    def calendar(self) -> dict:
        return self._request("/api/calendar")

    def weather(self) -> dict:
        return self._request("/api/weather")
