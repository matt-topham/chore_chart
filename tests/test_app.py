from __future__ import annotations

import json
import tempfile
import threading
import unittest
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from chore_app.db import connect_db
from chore_app.scheduler import initial_due_date, next_due_date, normalize_frequency, parse_weekdays
from chore_app.server import build_server


class SchedulerTests(unittest.TestCase):
    def test_normalizes_quarterly_typo(self):
        self.assertEqual(normalize_frequency("Quaterly"), "Quarterly")

    def test_parses_multiple_weekdays(self):
        self.assertEqual(parse_weekdays("Wednesday, Saturday"), [2, 5])

    def test_daily_is_due_next_day(self):
        chore = {"frequency": "Daily", "preferred_day": "Every Day", "first_due": "2026-08-02"}
        self.assertEqual(next_due_date(chore, date(2026, 8, 2)), date(2026, 8, 3))

    def test_weekly_moves_to_next_saturday(self):
        chore = {"frequency": "Weekly", "preferred_day": "Saturday", "first_due": "2026-08-08"}
        self.assertEqual(next_due_date(chore, date(2026, 8, 10)), date(2026, 8, 15))

    def test_monthly_rolls_to_preferred_day(self):
        chore = {"frequency": "Monthly", "preferred_day": "Saturday", "first_due": "2026-08-08"}
        self.assertEqual(next_due_date(chore, date(2026, 8, 8)), date(2026, 9, 12))

    def test_initial_monthly_chores_are_staggered(self):
        self.assertEqual(initial_due_date("Monthly", "Saturday", date(2026, 8, 2), 1), date(2026, 8, 15))


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.base_dir = Path(__file__).resolve().parent.parent
        cls.database = Path(cls.temp_dir.name) / "test.db"
        cls.server = build_server(
            "127.0.0.1",
            0,
            database_path=cls.database,
            workbook_path=cls.base_dir / "data/Apartment Routine.xlsx",
            base_dir=cls.base_dir,
            timezone_name="America/Denver",
            upcoming_days=7,
        )
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp_dir.cleanup()

    def request_json(self, path: str, method: str = "GET", data: dict | None = None):
        body = json.dumps(data).encode() if data is not None else None
        request = Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())

    def test_import_and_completion_flow(self):
        status, health = self.request_json("/health")
        self.assertEqual(status, 200)
        self.assertEqual(health, {"ok": True})

        status, payload = self.request_json("/api/chores?date=2026-08-02")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["due"]), 7)
        self.assertEqual(payload["counts"]["completed"], 0)

        chore_id = payload["due"][0]["id"]
        _, completed = self.request_json(f"/api/chores/{chore_id}/complete", "POST", {})
        completion_id = completed["completion_id"]

        _, after = self.request_json("/api/chores")
        self.assertEqual(after["counts"]["completed"], 1)

        self.request_json(f"/api/completions/{completion_id}", "DELETE")
        _, final = self.request_json("/api/chores")
        self.assertEqual(final["counts"]["completed"], 0)

        with connect_db(self.database) as db:
            total = db.execute("SELECT COUNT(*) FROM chores").fetchone()[0]
            self.assertEqual(total, 53)
            tidy = db.execute("SELECT task FROM chores WHERE task='Tidy Bathroom'").fetchone()
            mattress = db.execute("SELECT area FROM chores WHERE task='Vacuum Mattress'").fetchone()
            quarterly = db.execute("SELECT COUNT(*) FROM chores WHERE frequency='Quarterly'").fetchone()[0]
            self.assertIsNotNone(tidy)
            self.assertEqual(mattress["area"], "Bedroom")
            self.assertEqual(quarterly, 7)


if __name__ == "__main__":
    unittest.main()
