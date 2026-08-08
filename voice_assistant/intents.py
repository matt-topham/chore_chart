from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

from .client import DashboardClient


@dataclass
class AssistantResult:
    spoken: str
    action: str = "none"
    success: bool = True


def normalize(text: str) -> str:
    text = text.lower().replace("’", "'")
    text = re.sub(r"[^a-z0-9' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


class IntentHandler:
    def __init__(self, client: DashboardClient, timezone_name: str = "America/Los_Angeles"):
        self.client = client
        self.timezone = ZoneInfo(timezone_name)

    def handle(self, raw_command: str) -> AssistantResult:
        command = normalize(raw_command)
        if not command:
            return AssistantResult("I didn't catch that.", success=False)

        command = re.sub(r"^(hey )?bellamy[ ,]*", "", command).strip()

        try:
            result = self._complete_task(command)
            if result: return result
            result = self._add_grocery(command)
            if result: return result
            result = self._add_reminder(command)
            if result: return result
            result = self._add_note(command)
            if result: return result
            result = self._calendar_query(command)
            if result: return result
            result = self._task_query(command)
            if result: return result
            result = self._weather_query(command)
            if result: return result
            result = self._grocery_query(command)
            if result: return result
            if command in {"help", "what can you do", "what can you do for me"}:
                return AssistantResult("I can complete chores, add groceries, add reminders and notes, and read your calendar, chores, groceries, or weather.", "help")
        except RuntimeError:
            return AssistantResult("I couldn't reach the home dashboard.", "error", False)

        return AssistantResult("I don't know that command yet.", "unknown", False)

    def _complete_task(self, command: str) -> AssistantResult | None:
        patterns = [
            r"^(?:mark|check|check off|complete|finish) (.+?)(?: as)? done$",
            r"^(?:mark|check|check off|complete|finish) (.+)$",
            r"^(.+?) is done$",
        ]
        task_name = None
        for pattern in patterns:
            match = re.match(pattern, command)
            if match:
                task_name = match.group(1).strip()
                break
        if not task_name:
            return None

        payload = self.client.chores()
        candidates = payload.get("due", []) + payload.get("upcoming", [])
        match = self._best_task(task_name, candidates)
        if match is None:
            return AssistantResult(f"I couldn't find a task matching {task_name}.", "complete_chore", False)
        self.client.complete_chore(int(match["id"]))
        return AssistantResult(f"{match['task']} marked complete.", "complete_chore")

    def _best_task(self, spoken: str, candidates: list[dict]) -> dict | None:
        needle = normalize(spoken)
        if not needle or not candidates:
            return None
        scored: list[tuple[float, dict]] = []
        needle_tokens = set(needle.split())
        for item in candidates:
            task = normalize(str(item.get("task", "")))
            task_tokens = set(task.split())
            ratio = SequenceMatcher(None, needle, task).ratio()
            overlap = len(needle_tokens & task_tokens) / max(1, len(needle_tokens))
            containment = 1.0 if needle in task or task in needle else 0.0
            score = max(ratio, overlap * 0.9, containment)
            scored.append((score, item))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1] if scored and scored[0][0] >= 0.48 else None

    def _add_grocery(self, command: str) -> AssistantResult | None:
        patterns = [
            r"^add (.+?) to (?:the )?(?:grocery list|groceries|shopping list)$",
            r"^put (.+?) on (?:the )?(?:grocery list|groceries|shopping list)$",
            r"^add (.+?) to groceries$",
        ]
        value = None
        for pattern in patterns:
            match = re.match(pattern, command)
            if match:
                value = match.group(1).strip()
                break
        if not value:
            return None

        items = [part.strip() for part in re.split(r",|\band\b", value) if part.strip()]
        if not items:
            return AssistantResult("I didn't hear a grocery item.", "add_grocery", False)
        for item in items:
            self.client.add_grocery(item, self._grocery_category(item))
        if len(items) == 1:
            return AssistantResult(f"{items[0].capitalize()} added to the grocery list.", "add_grocery")
        return AssistantResult(f"Added {len(items)} items to the grocery list.", "add_grocery")

    @staticmethod
    def _grocery_category(item: str) -> str:
        words = set(normalize(item).split())
        if words & {"milk", "cheese", "yogurt", "cream", "butter", "eggs"}: return "Dairy"
        if words & {"apple", "apples", "banana", "bananas", "lettuce", "tomato", "tomatoes", "onion", "onions", "potato", "potatoes", "fruit", "vegetables"}: return "Produce"
        if words & {"chicken", "beef", "steak", "pork", "turkey", "sausage", "bacon"}: return "Meat"
        if words & {"soap", "detergent", "towels", "towel", "toilet", "cleaner", "trash", "bags"}: return "Household"
        return "Other"

    def _add_reminder(self, command: str) -> AssistantResult | None:
        title = when = None
        match = re.match(r"^remind me (?:to )?(.+?) (?:on|for) (.+)$", command)
        if match:
            title, when = match.group(1).strip(), match.group(2).strip()
        else:
            match = re.match(r"^remind me (today|tomorrow|(?:next )?[a-z]+) to (.+)$", command)
            if match:
                when, title = match.group(1).strip(), match.group(2).strip()
            else:
                match = re.match(r"^remind me to (.+?) (today|tomorrow|(?:next )?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))$", command)
                if match:
                    title, when = match.group(1).strip(), match.group(2).strip()
        if not title or not when:
            return None

        due = self._parse_date(when)
        if due is None:
            return AssistantResult(f"I couldn't understand the reminder date {when}.", "add_reminder", False)
        self.client.add_reminder(title, due.isoformat())
        return AssistantResult(f"Reminder added for {due.strftime('%A, %B')} {due.day}: {title}.", "add_reminder")

    def _add_note(self, command: str) -> AssistantResult | None:
        match = re.match(r"^(?:add|make|create) (?:a )?(?:household )?note(?: that)? (.+)$", command)
        if not match:
            return None
        body = match.group(1).strip()
        if not body:
            return AssistantResult("I didn't hear the note.", "add_note", False)
        self.client.add_note(body)
        return AssistantResult("Household note added.", "add_note")

    def _parse_date(self, text: str) -> date | None:
        text = normalize(text)
        today = datetime.now(self.timezone).date()
        if text == "today": return today
        if text == "tomorrow": return today + timedelta(days=1)

        weekdays = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        weekday_text = text.removeprefix("next ")
        if weekday_text in weekdays:
            ahead = (weekdays[weekday_text] - today.weekday()) % 7
            if ahead == 0: ahead = 7
            return today + timedelta(days=ahead)

        ordinal_words = {
            "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
            "eleventh": "11", "twelfth": "12", "thirteenth": "13", "fourteenth": "14", "fifteenth": "15", "sixteenth": "16", "seventeenth": "17", "eighteenth": "18", "nineteenth": "19", "twentieth": "20",
            "twenty first": "21", "twenty second": "22", "twenty third": "23", "twenty fourth": "24", "twenty fifth": "25", "twenty sixth": "26", "twenty seventh": "27", "twenty eighth": "28", "twenty ninth": "29", "thirtieth": "30", "thirty first": "31",
        }
        for word, number in sorted(ordinal_words.items(), key=lambda x: len(x[0]), reverse=True):
            text = re.sub(rf"\b{re.escape(word)}\b", number, text)
        text = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", text)

        for fmt in ("%B %d", "%b %d", "%m/%d", "%m-%d", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                if "%Y" not in fmt:
                    parsed = parsed.replace(year=today.year)
                    if parsed < today:
                        parsed = parsed.replace(year=today.year + 1)
                return parsed
            except ValueError:
                pass
        return None

    def _calendar_query(self, command: str) -> AssistantResult | None:
        if "calendar" not in command and "schedule" not in command:
            return None
        target = datetime.now(self.timezone).date()
        label = "today"
        if "tomorrow" in command:
            target += timedelta(days=1); label = "tomorrow"
        payload = self.client.calendar()
        if not payload.get("configured"):
            return AssistantResult("Google Calendar is not connected yet.", "calendar", False)
        events = [event for event in payload.get("events", []) if datetime.fromisoformat(event["start"]).astimezone(self.timezone).date() == target]
        if not events:
            return AssistantResult(f"You have nothing on the calendar {label}.", "calendar")
        names = [event.get("title", "Untitled event") for event in events[:4]]
        ending = "" if len(events) <= 4 else f", plus {len(events)-4} more"
        return AssistantResult(f"You have {len(events)} event{'s' if len(events) != 1 else ''} {label}: " + ", ".join(names) + ending + ".", "calendar")

    def _task_query(self, command: str) -> AssistantResult | None:
        if not any(phrase in command for phrase in ("what chores", "which chores", "what tasks", "which tasks", "chores today", "tasks today", "what do i need to do")):
            return None
        payload = self.client.chores(); due = payload.get("due", [])
        if not due:
            return AssistantResult("You don't have any chores due right now.", "chores")
        names = [item["task"] for item in due[:5]]
        ending = "" if len(due) <= 5 else f", plus {len(due)-5} more"
        return AssistantResult(f"You have {len(due)} chore{'s' if len(due) != 1 else ''} due: " + ", ".join(names) + ending + ".", "chores")

    def _weather_query(self, command: str) -> AssistantResult | None:
        if "weather" not in command and "temperature" not in command:
            return None
        payload = self.client.weather()
        if not payload.get("configured") or payload.get("error"):
            return AssistantResult("Weather isn't available right now.", "weather", False)
        current = payload.get("current", {}); daily = payload.get("daily", [])
        temp = current.get("temperature")
        if temp is None:
            return AssistantResult("Weather isn't available right now.", "weather", False)
        response = f"It's {round(temp)} degrees outside"
        if daily:
            high, low = daily[0].get("high"), daily[0].get("low")
            if high is not None and low is not None:
                response += f", with a high of {round(high)} and a low of {round(low)}"
        return AssistantResult(response + ".", "weather")

    def _grocery_query(self, command: str) -> AssistantResult | None:
        if not any(phrase in command for phrase in ("what's on the grocery", "whats on the grocery", "what is on the grocery", "what's on groceries", "grocery list", "shopping list")):
            return None
        if command.startswith(("add ", "put ")):
            return None
        items = [item for item in self.client.groceries() if not item.get("completed")]
        if not items:
            return AssistantResult("The grocery list is empty.", "groceries")
        names = [item["item"] for item in items[:7]]
        ending = "" if len(items) <= 7 else f", plus {len(items)-7} more"
        return AssistantResult("Your grocery list has " + ", ".join(names) + ending + ".", "groceries")
