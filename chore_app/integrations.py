from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


def _fetch_text(url: str, timeout: int = 8) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "ChoreDashboard/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def get_weather(timezone_name: str) -> dict:
    lat = os.environ.get("DASHBOARD_LATITUDE", "").strip()
    lon = os.environ.get("DASHBOARD_LONGITUDE", "").strip()
    if not lat or not lon:
        return {"configured": False, "error": "Set DASHBOARD_LATITUDE and DASHBOARD_LONGITUDE"}

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&current=temperature_2m,apparent_temperature,weather_code,precipitation,wind_speed_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch"
        f"&timezone={urllib.parse.quote(timezone_name)}&forecast_days=5"
    )
    try:
        payload = json.loads(_fetch_text(url))
    except Exception as exc:
        return {"configured": True, "error": str(exc)}

    current = payload.get("current", {})
    daily = payload.get("daily", {})
    days = []
    dates = daily.get("time", [])
    for i, day in enumerate(dates):
        days.append({
            "date": day,
            "code": _safe_index(daily.get("weather_code", []), i),
            "high": _safe_index(daily.get("temperature_2m_max", []), i),
            "low": _safe_index(daily.get("temperature_2m_min", []), i),
            "rain_probability": _safe_index(daily.get("precipitation_probability_max", []), i),
        })
    return {
        "configured": True,
        "current": {
            "temperature": current.get("temperature_2m"),
            "feels_like": current.get("apparent_temperature"),
            "code": current.get("weather_code"),
            "precipitation": current.get("precipitation"),
            "wind": current.get("wind_speed_10m"),
        },
        "daily": days,
    }


def _safe_index(values, index):
    try:
        return values[index]
    except (IndexError, TypeError):
        return None


def _unfold_ics(text: str) -> list[str]:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    unfolded: list[str] = []
    for line in lines:
        if line.startswith((" ", "\t")) and unfolded:
            unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _parse_ics_datetime(value: str, params: str, local_tz: ZoneInfo) -> datetime:
    if "VALUE=DATE" in params or (len(value) == 8 and "T" not in value):
        return datetime.strptime(value[:8], "%Y%m%d").replace(tzinfo=local_tz)
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(local_tz)
    tz = local_tz
    for part in params.split(";"):
        if part.startswith("TZID="):
            try:
                tz = ZoneInfo(part.removeprefix("TZID="))
            except Exception:
                tz = local_tz
    return datetime.strptime(value[:15], "%Y%m%dT%H%M%S").replace(tzinfo=tz).astimezone(local_tz)


def get_calendar(timezone_name: str, days: int = 7) -> dict:
    url = os.environ.get("GOOGLE_CALENDAR_ICAL_URL", "").strip()
    if not url:
        return {"configured": False, "events": [], "error": "Set GOOGLE_CALENDAR_ICAL_URL"}
    local_tz = ZoneInfo(timezone_name)
    now = datetime.now(local_tz)
    end_window = now + timedelta(days=days)
    try:
        lines = _unfold_ics(_fetch_text(url))
    except Exception as exc:
        return {"configured": True, "events": [], "error": str(exc)}

    events = []
    event: dict[str, str] | None = None
    for line in lines:
        if line == "BEGIN:VEVENT":
            event = {}
            continue
        if line == "END:VEVENT" and event is not None:
            try:
                start_key = next(k for k in event if k.startswith("DTSTART"))
                start = _parse_ics_datetime(event[start_key], start_key, local_tz)
                if start.date() >= now.date() and start <= end_window:
                    all_day = "VALUE=DATE" in start_key or "T" not in event[start_key]
                    events.append({
                        "title": event.get("SUMMARY", "Untitled event").replace("\\,", ","),
                        "start": start.isoformat(),
                        "all_day": all_day,
                        "location": event.get("LOCATION", "").replace("\\,", ","),
                    })
            except Exception:
                pass
            event = None
            continue
        if event is not None and ":" in line:
            key, value = line.split(":", 1)
            if key.startswith(("DTSTART", "SUMMARY", "LOCATION")):
                event[key] = value

    events.sort(key=lambda item: item["start"])
    return {"configured": True, "events": events[:20]}
