"""Read a complete calendar window through gws, retaining the last good export."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def _pages(resource: str, params: dict, *, gws: str, config_dir: Path) -> list[dict]:
    env = os.environ.copy()
    env["GOOGLE_WORKSPACE_CLI_CONFIG_DIR"] = str(config_dir.expanduser())
    items = []
    seen_tokens = set()
    params = dict(params)
    # Paginate explicitly: --page-all has a default page limit which could silently
    # turn an incomplete response into an apparently empty part of the calendar.
    for _ in range(100):
        response = subprocess.run(
            [gws, "calendar", resource, "list", "--params", json.dumps(params),
             "--format", "json"],
            env=env, capture_output=True, text=True, check=True, timeout=60,
        )
        page = json.loads(response.stdout)
        if not isinstance(page, dict) or "error" in page:
            raise ValueError("Invalid calendar response")
        expected_kind = "calendar#calendarList" if resource == "calendarList" else "calendar#events"
        if page.get("kind") != expected_kind:
            raise ValueError("Unexpected calendar response kind")
        batch = page.get("items", [])
        if not isinstance(batch, list) or any(not isinstance(item, dict) for item in batch):
            raise ValueError("Invalid calendar items")
        items.extend(batch)
        token = page.get("nextPageToken")
        if not token:
            return items
        if not isinstance(token, str) or token in seen_tokens:
            raise ValueError("Invalid calendar pagination")
        seen_tokens.add(token)
        params["pageToken"] = token
    raise ValueError("Calendar pagination exceeded 100 pages; previous export retained")


def _event_time(value: dict) -> str:
    if not isinstance(value, dict):
        raise ValueError("Missing event time")
    if "dateTime" in value:
        instant = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if instant.tzinfo is None:
            if not value.get("timeZone"):
                raise ValueError("Event time must have a timezone")
            instant = instant.replace(tzinfo=ZoneInfo(value["timeZone"]))
        return instant.isoformat()
    if "date" in value:
        return date.fromisoformat(value["date"]).isoformat()
    raise ValueError("Missing event date or datetime")


def _project_event(event: dict) -> dict | None:
    status = event.get("status", "confirmed")
    if status not in {"confirmed", "tentative", "cancelled"}:
        raise ValueError("Invalid event status")
    # Google cancellation tombstones may have only an ID. This is a complete
    # replacement export, so absence correctly removes the previous event.
    if status == "cancelled":
        return None
    event_id, summary = event.get("id"), event.get("summary", "Untitled event")
    if not isinstance(event_id, str) or not event_id or not isinstance(summary, str):
        raise ValueError("Invalid event identity or summary")
    start, end = _event_time(event.get("start")), _event_time(event.get("end"))
    timed = "T" in start
    if timed != ("T" in end):
        raise ValueError("Event start and end must use the same time type")
    parse = datetime.fromisoformat if timed else date.fromisoformat
    if parse(end) <= parse(start):
        raise ValueError("Event end must follow start")
    location = event.get("location", "")
    if not isinstance(location, str):
        raise ValueError("Invalid event location")
    return {"id": event_id, "summary": summary, "start": start, "end": end,
            "status": status, "location": location}


def export_calendar(
    output: Path, *, config_dir: Path, calendar: str = "Family", days: int = 21,
    timezone: str = "America/New_York", gws: str = "gws", now: datetime | None = None,
) -> dict:
    """Fetch today in full plus following days; atomically replace only after validation."""
    if not 1 <= days <= 366:
        raise ValueError("Calendar window must be between 1 and 366 days")
    tz = ZoneInfo(timezone)
    instant = now or datetime.now(tz)
    if instant.tzinfo is None:
        raise ValueError("Export clock must have a timezone")
    today = instant.astimezone(tz).date()
    end_exclusive = today + timedelta(days=days)
    transport = {"gws": gws, "config_dir": config_dir}
    calendars = _pages("calendarList", {"maxResults": 250}, **transport)
    matches = [item for item in calendars if not item.get("deleted") and (
        item.get("id") == calendar or item.get("summaryOverride", item.get("summary")) == calendar
    )]
    if len(matches) != 1 or not isinstance(matches[0].get("id"), str):
        raise ValueError(f"Calendar {calendar!r} must identify exactly one calendar")
    selected = matches[0]
    events = _pages("events", {
        "calendarId": selected["id"], "singleEvents": True, "showDeleted": False,
        "orderBy": "startTime", "maxResults": 2500, "timeZone": timezone,
        "timeMin": datetime.combine(today, time.min, tz).isoformat(),
        "timeMax": datetime.combine(end_exclusive, time.min, tz).isoformat(),
    }, **transport)
    projected = [item for event in events if (item := _project_event(event)) is not None]
    payload = {
        "timezone": timezone,
        "checked_at": (instant if now is not None else datetime.now(tz)).isoformat(),
        "start_date": today.isoformat(),
        "end_date": (end_exclusive - timedelta(days=1)).isoformat(),
        "source": {"provider": "google-calendar", "calendar_id": selected["id"],
                   "calendar_name": selected.get("summary", calendar),
                   "config_dir": str(config_dir.expanduser())},
        "events": projected,
    }
    content = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    output = output.expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=f".{output.name}.", delete=False) as temp:
            temp_path = Path(temp.name)
            temp.write(content)
            temp.flush()
            os.fsync(temp.fileno())
        os.replace(temp_path, output)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return payload
