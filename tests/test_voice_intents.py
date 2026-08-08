from __future__ import annotations

import unittest

from voice_assistant.intents import IntentHandler


class FakeClient:
    def __init__(self):
        self.completed = []
        self.added_groceries = []
        self.reminders = []
        self.notes = []

    def chores(self):
        return {
            "due": [
                {"id": 1, "task": "Unload Dishwasher", "area": "Kitchen"},
                {"id": 2, "task": "Vacuum Living Room", "area": "Living Room"},
            ],
            "upcoming": [],
        }

    def complete_chore(self, chore_id):
        self.completed.append(chore_id); return {"ok": True}

    def groceries(self):
        return [{"item": "Coffee", "completed": 0}, {"item": "Bread", "completed": 0}]

    def add_grocery(self, item, category="Other", quantity=""):
        self.added_groceries.append((item, category)); return {"ok": True}

    def add_reminder(self, title, due_date, notes=""):
        self.reminders.append((title, due_date)); return {"ok": True}

    def add_note(self, body):
        self.notes.append(body); return {"ok": True}

    def calendar(self):
        return {"configured": True, "events": []}

    def weather(self):
        return {"configured": True, "current": {"temperature": 71.4}, "daily": [{"high": 77.2, "low": 55.1}]}


class VoiceIntentTests(unittest.TestCase):
    def setUp(self):
        self.client = FakeClient()
        self.handler = IntentHandler(self.client, "America/Los_Angeles")

    def test_completes_fuzzy_chore(self):
        result = self.handler.handle("mark dishwasher done")
        self.assertTrue(result.success)
        self.assertEqual(self.client.completed, [1])

    def test_adds_multiple_groceries(self):
        result = self.handler.handle("add milk and bananas to groceries")
        self.assertTrue(result.success)
        self.assertEqual([item[0] for item in self.client.added_groceries], ["milk", "bananas"])

    def test_adds_note(self):
        result = self.handler.handle("add a note maintenance is coming Tuesday")
        self.assertTrue(result.success)
        self.assertEqual(self.client.notes, ["maintenance is coming tuesday"])

    def test_reads_weather(self):
        result = self.handler.handle("what's the weather")
        self.assertTrue(result.success)
        self.assertIn("71 degrees", result.spoken)

    def test_reads_grocery_list(self):
        result = self.handler.handle("what's on the grocery list")
        self.assertTrue(result.success)
        self.assertIn("Coffee", result.spoken)
        self.assertIn("Bread", result.spoken)


if __name__ == "__main__":
    unittest.main()
