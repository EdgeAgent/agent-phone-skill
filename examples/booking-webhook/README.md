# Booking webhook example

A small, working reference implementation of the skill's booking loop:

```
caller ⇄ assistant ──tool call──▶ this webhook ──▶ calendar event
                                              └──▶ confirmation SMS (Twilio)
```

## Run it

```bash
python3 server.py            # http://127.0.0.1:8080, stdlib only
```

Optional — enables the confirmation SMS (without these, bookings still
succeed and the result honestly reports `sms_detail: sms-not-configured`):

```bash
export TWILIO_ACCOUNT_SID="ACxxxxxxxx"
export TWILIO_AUTH_TOKEN="your-auth-token"
export TWILIO_FROM_NUMBER="+15550100"
```

## Test it

```bash
curl -s http://127.0.0.1:8080/health

curl -s -X POST http://127.0.0.1:8080/tools/book_appointment \
  -H 'Content-Type: application/json' \
  -d '{"name":"Jordan Lee","service":"Initial consultation",
       "date":"2026-11-20","time":"14:30",
       "timezone":"America/Toronto","phone":"+15550199",
       "notes":"First visit"}'
```

Booking the same slot twice returns `ok: false` with a slot-taken error
— the assistant should offer alternatives, never double-book.

## Data contract

| Field | Type | Notes |
|---|---|---|
| `name` | string | Caller's full name |
| `service` | string | Must be a service the business offers |
| `date` | string | `YYYY-MM-DD` |
| `time` | string | `HH:MM`, 24h, in `timezone` |
| `timezone` | string | IANA name, e.g. `America/Toronto` |
| `phone` | string | E.164 — used for the confirmation SMS |
| `notes` | string | Optional |

## Wiring it to Vapi

1. Run this server behind a public HTTPS URL (a tunnel for testing).
2. On the assistant, add a function tool named `book_appointment` with
   the fields above as parameters, and set the tool's server URL to
   `https://<your-host>/tools/book_appointment`.
3. The server accepts the Vapi tool-call envelope
   (`message.toolCalls[0].function.arguments`) and replies in Vapi's
   `results` shape.

## Going to production

- Replace `write_calendar_event()` with a real Google Calendar
  `events.insert` (the event dict already matches the API shape), or
  your calendar provider's equivalent.
- Verify webhook signatures, require HTTPS, rate-limit the endpoint.
- Replace the JSON-file store with your real availability source —
  booking correctness is only as good as this check.
