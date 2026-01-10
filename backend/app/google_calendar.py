# backend/app/google_calendar.py

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from .models import StoredAppointment
from typing import Optional
from typing import List, Tuple





CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")

# ENV CONFIG
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# token.json is expected in the backend/ directory (one level above app/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

# Fixed IST timezone (Asia/Kolkata)
IST = timezone(timedelta(hours=5, minutes=30))


def _ensure_ist(dt: datetime) -> datetime:
    """
    Ensure datetime is timezone-aware in IST (Asia/Kolkata).
    - If naive: assume it's IST.
    - If already aware: return as-is.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt


def _to_rfc3339_utc(dt: datetime) -> str:
    """
    Convert a datetime to an RFC3339 string in UTC for Google Calendar queries.
    """
    dt_ist = _ensure_ist(dt)
    dt_utc = dt_ist.astimezone(timezone.utc)
    return dt_utc.isoformat()


def get_calendar_service():
    """
    Build and return an authenticated Google Calendar service.

    Precondition: backend/token.json already exists (generated once via OAuth).
    """
    if not os.path.exists(TOKEN_PATH):
        raise RuntimeError(
            f"token.json not found at {TOKEN_PATH}. "
            "Run the Google Calendar Python quickstart once to generate it."
        )

    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    # Refresh token if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_PATH, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

    service = build("calendar", "v3", credentials=creds)
    return service


def is_slot_free(start: datetime, end: datetime) -> bool:
    """
    Check if [start, end) is free in the configured calendar.

    Returns:
        True  -> no overlapping *timed* events (slot free)
        False -> at least one timed event overlaps (slot busy)

    All-day events (with only 'date' but no 'dateTime') are ignored,
    so holidays or all-day reminders don't block the slot.
    """
    service = get_calendar_service()

    time_min = _to_rfc3339_utc(start)
    time_max = _to_rfc3339_utc(end)

    events_result = (
        service.events()
        .list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    items = events_result.get("items", []) or []

    # 🔍 Filter out all-day events – we only care about ones with 'dateTime'
    timed_events = []
    for ev in items:
        start_info = ev.get("start", {})
        end_info = ev.get("end", {})
        if "dateTime" in start_info or "dateTime" in end_info:
            timed_events.append(ev)

    # 🔥 Debug logging so you can see what's going on
    print(">>> is_slot_free called")
    print(f"    time_min: {time_min}")
    print(f"    time_max: {time_max}")
    print(f"    total events returned: {len(items)}")
    print(f"    timed events considered: {len(timed_events)}")
    for ev in timed_events:
        print("    - summary:", ev.get("summary"))
        print("      start:", ev.get("start"))
        print("      end  :", ev.get("end"))

    # Slot is free if there are no timed events overlapping
    return len(timed_events) == 0


# Same working hours as agent.py (keep in sync manually)
CLINIC_OPEN_HOUR = 9
CLINIC_LUNCH_START = 13
CLINIC_LUNCH_END = 14
CLINIC_CLOSE_HOUR = 18


def _is_within_working_hours_local(dt: datetime) -> bool:
    """
    Local helper for calendar-based suggestions.
    dt may be any timezone; we convert to IST for comparison.
    """
    local = dt.astimezone(IST)
    h = local.hour + local.minute / 60.0

    if h < CLINIC_OPEN_HOUR or h >= CLINIC_CLOSE_HOUR:
        return False

    if CLINIC_LUNCH_START <= h < CLINIC_LUNCH_END:
        return False

    return True


def find_alternative_slots(
    requested_start: datetime,
    duration_minutes: int = 30,
    max_suggestions: int = 4,
) -> List[Tuple[datetime, datetime]]:
    """
    Find up to `max_suggestions` nearby free slots around the requested_start,
    using Google Calendar availability, but only within clinic working hours.
    """
    now_ist = datetime.now(IST)
    slot_delta = timedelta(minutes=duration_minutes)

    suggestions: List[Tuple[datetime, datetime]] = []

    for i in range(-2, 9):
        if i == 0:
            continue

        candidate_start = requested_start + i * slot_delta
        candidate_end = candidate_start + slot_delta

        # Ignore past slots
        if candidate_start < now_ist:
            continue

        # Enforce working hours
        if not (_is_within_working_hours_local(candidate_start) and _is_within_working_hours_local(candidate_end)):
            continue

        try:
            if is_slot_free(candidate_start, candidate_end):
                suggestions.append((candidate_start, candidate_end))
        except Exception as e:
            print(">>> find_alternative_slots: is_slot_free error:", repr(e))
            continue

        if len(suggestions) >= max_suggestions:
            break

    return suggestions





def create_calendar_event(appt: StoredAppointment) -> str:
    """
    Create a Google Calendar event for the given StoredAppointment.

    Returns:
        event_id (str): The created Google Calendar event's ID.
    """
    service = get_calendar_service()

    start_local = _ensure_ist(appt.start_time)
    end_local = _ensure_ist(appt.end_time)

    event_body = {
        "summary": f"Dental appointment - {appt.reason}",
        "description": f"Patient: {appt.patient_name} (user_id: {appt.user_id})",
        "start": {
            "dateTime": start_local.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end_local.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
    }

    created = (
        service.events()
        .insert(
            calendarId=GOOGLE_CALENDAR_ID,
            body=event_body,
        )
        .execute()
    )

    return created["id"]

def update_calendar_event(stored: StoredAppointment) -> str:
    """
    Move an existing Google Calendar event to stored.start_time / stored.end_time.
    Does NOT create a new event.
    """
    if not stored.google_event_id:
        raise ValueError("Cannot update calendar event: google_event_id is missing.")

    service = get_calendar_service()

    # Fetch existing event
    event = service.events().get(
        calendarId=CALENDAR_ID,
        eventId=stored.google_event_id,
    ).execute()

    # Update start/end times
    event["start"]["dateTime"] = stored.start_time.isoformat()
    event["end"]["dateTime"] = stored.end_time.isoformat()

    updated = service.events().update(
        calendarId=CALENDAR_ID,
        eventId=stored.google_event_id,
        body=event,
    ).execute()

    # Return event id (unchanged, but kept for consistency)
    return updated["id"]


def cancel_calendar_event(stored: StoredAppointment) -> None:
    """
    Cancel/delete the Google Calendar event for this appointment, if any.
    Does nothing if google_event_id is missing.
    """
    if not stored.google_event_id:
        print(">>> cancel_calendar_event: no google_event_id on stored appointment, nothing to cancel.")
        return

    service = get_calendar_service()

    try:
        service.events().delete(
            calendarId=GOOGLE_CALENDAR_ID,
            eventId=stored.google_event_id,
        ).execute()
        print(f">>> cancel_calendar_event: deleted event {stored.google_event_id}")
    except Exception as e:
        # Don't hard-fail the whole flow if calendar deletion fails
        print(f">>> cancel_calendar_event ERROR for {stored.google_event_id}:", repr(e))
