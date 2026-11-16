#!/usr/bin/env python3
"""
Booking webhook example for the Agent Phone Skill.

Receives a `book_appointment` tool call from a voice assistant (Vapi
shape shown; the payload contract is platform-agnostic), validates it,
checks the slot against a local calendar store, writes the event, and
sends a confirmation SMS via Twilio.

Stdlib only — no pip installs. Run:

    export TWILIO_ACCOUNT_SID="ACxxxxxxxx"        # optional: enables SMS
    export TWILIO_AUTH_TOKEN="your-auth-token"    # optional
    export TWILIO_FROM_NUMBER="+15550100"         # your Twilio number
    python3 server.py            # listens on http://127.0.0.1:8080

Endpoints:
    POST /tools/book_appointment   the tool-call webhook
    GET  /health                   liveness check

Calendar: events are stored in ./calendar.json (created on first write).
The stored record mirrors the Google Calendar API event shape so the
`write_calendar_event()` function can be swapped for a real Google
Calendar insert (events.insert) without changing the contract.

SECURITY: this is a teaching example. In production, verify the
provider's webhook signature, require HTTPS, and never log secrets.
"""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

CALENDAR_FILE = Path(__file__).with_name("calendar.json")
DEFAULT_DURATION_MIN = 30


# ---------------------------------------------------------------- store

def load_events():
    if CALENDAR_FILE.exists():
        return json.loads(CALENDAR_FILE.read_text())
    return []


def save_events(events):
    CALENDAR_FILE.write_text(json.dumps(events, indent=2))


def slot_taken(events, start_iso, end_iso):
    """Naive overlap check on ISO datetimes in the same timezone."""
    for ev in events:
        if start_iso < ev["end"]["dateTime"] and end_iso > ev["start"]["dateTime"]:
            return True
    return False


# ------------------------------------------------------------- calendar

def build_calendar_event(booking):
    """Return a Google Calendar API-shaped event resource."""
    tz = booking.get("timezone", "UTC")
    start = datetime.fromisoformat(f"{booking['date']}T{booking['time']}")
    end = start + timedelta(minutes=DEFAULT_DURATION_MIN)
    return {
        "summary": f"{booking['service']} — {booking['name']}",
        "description": (
            f"Booked by phone assistant.\n"
            f"Customer: {booking['name']}\n"
            f"Phone: {booking['phone']}\n"
            f"Notes: {booking.get('notes', '')}"
        ),
        "start": {"dateTime": start.isoformat(), "timeZone": tz},
        "end": {"dateTime": end.isoformat(), "timeZone": tz},
        # A real Google Calendar insert would also carry attendees,
        # reminders, and conferenceData as needed.
    }


def write_calendar_event(event):
    """Persist the event. Swap this body for a Google Calendar API
    `events.insert` call in production; the shape already matches."""
    events = load_events()
    events.append(event)
    save_events(events)
    return event


# ------------------------------------------------------------------ sms

def send_confirmation_sms(booking, event):
    """Send the confirmation SMS via Twilio's REST API.

    Returns (ok, detail). If Twilio env vars are unset, returns
    (False, 'sms-not-configured') and the booking still succeeds —
    the caller must be told the truth either way."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    if not (sid and token and from_number):
        return False, "sms-not-configured"

    when = f"{booking['date']} at {booking['time']} ({booking.get('timezone', 'UTC')})"
    body = (
        f"You're booked: {booking['service']} on {when}. "
        f"Reply to this text to reschedule or cancel."
    )
    data = urllib.parse.urlencode(
        {"From": from_number, "To": booking["phone"], "Body": body}
    ).encode()
    req = urllib.request.Request(
        f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
        data=data,
        method="POST",
    )
    import base64
    cred = base64.b64encode(f"{sid}:{token}".encode()).decode()
    req.add_header("Authorization", f"Basic {cred}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode())
            return True, payload.get("sid", "sent")
    except Exception as exc:  # report, never fake a confirmation
        return False, f"sms-failed: {exc}"


# -------------------------------------------------------------- booking

REQUIRED_FIELDS = ["name", "service", "date", "time", "phone"]


def handle_booking(args):
    """Validate -> availability -> write -> confirm. Returns a result
    dict the assistant can speak back to the caller."""
    missing = [f for f in REQUIRED_FIELDS if not str(args.get(f, "")).strip()]
    if missing:
        return {"ok": False, "error": f"Missing fields: {', '.join(missing)}"}

    event = build_calendar_event(args)
    events = load_events()
    if slot_taken(events, event["start"]["dateTime"], event["end"]["dateTime"]):
        return {"ok": False, "error": "That slot is already booked. Offer the caller the nearest alternatives."}

    write_calendar_event(event)
    sms_ok, sms_detail = send_confirmation_sms(args, event)
    return {
        "ok": True,
        "message": (
            f"Booked {args['service']} for {args['name']} on "
            f"{args['date']} at {args['time']}."
        ),
        "confirmation_sms_sent": sms_ok,
        "sms_detail": sms_detail,
        "event": event,
    }


# ---------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/tools/book_appointment":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid JSON"})
            return

        # Vapi tool-call shape: {"message": {"toolCalls": [{"id": ...,
        # "function": {"name": "book_appointment", "arguments": {...}}}]}}
        # A plain {"name": ..., "service": ...} body is also accepted so
        # the endpoint is easy to test with curl.
        args = payload
        message = payload.get("message") or {}
        tool_calls = message.get("toolCalls") or []
        if tool_calls:
            fn = tool_calls[0].get("function") or {}
            raw = fn.get("arguments") or {}
            args = json.loads(raw) if isinstance(raw, str) else raw
            result = handle_booking(args)
            self._json(200, {"results": [{
                "toolCallId": tool_calls[0].get("id"),
                "result": json.dumps(result),
            }]})
            return

        self._json(200, handle_booking(args))

    def log_message(self, fmt, *fmt_args):  # keep stdout clean
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % fmt_args))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"Booking webhook listening on http://127.0.0.1:{port}")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
