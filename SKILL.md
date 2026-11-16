# Agent Phone Skill — AI Voice Calls, SMS & Appointment Booking (Twilio + Vapi)

## Purpose

Give any AI agent a phone: place and receive real phone calls, send and
receive SMS, and book appointments while on a call — using **Vapi** for
conversational AI voice and **Twilio** for telephony plumbing (numbers,
plain calls, SMS). The skill is provider-shaped but vendor-honest: Vapi
handles the talking, Twilio handles the pipes, and either can be swapped
without rewriting the agent's workflow.

## When to use this skill

Use it when the task involves any of:

- Placing an **outbound AI voice call** (sales, follow-up, reminders,
  surveys) where the agent must hold a real conversation.
- **Receiving inbound calls** with an AI receptionist that answers,
  qualifies, and helps the caller.
- **Booking an appointment during a call** — collect details, write a
  calendar event, confirm by SMS.
- Sending or receiving **SMS** (confirmations, reminders, follow-ups).
- Placing a **plain scripted voice call** (a fixed message read aloud)
  without a conversational model.

Do NOT use it for: email (use an email skill), chat messaging apps
(WhatsApp/Telegram/etc. have their own APIs and rules), or designing a
sales script's copy (write the script first, then use this skill to run
it). Do not use it to call anyone the user has not approved calling.

## Capabilities at a glance

| Capability | Vapi | Twilio |
|---|---|---|
| Outbound conversational AI call | ✅ primary | via TwiML + your own STT/LLM/TTS |
| Outbound scripted (fixed message) call | ✅ | ✅ primary |
| Inbound AI receptionist | ✅ assign assistant to number | ✅ TwiML/webhook routing |
| SMS send / receive | ❌ (use Twilio) | ✅ primary |
| In-call booking tool | ✅ tool calls → webhook | ✅ Gather + webhook |
| Call records (status, cost, transcript, recording) | ✅ rich | ✅ (recording/transcript add-ons) |

## Inputs

- **Who to call / who is calling**: E.164 numbers (`+1 555 0100` style),
  names, and per-contact context variables.
- **The script or assistant prompt**: opener, pitch/flow, objection
  handling, hard exits.
- **A call list with provenance**: where each number came from and why
  calling it is legitimate.
- **Booking parameters** (if booking): services offered, hours, timezone,
  calendar target, confirmation template.
- **Credentials** — from environment variables or a secret store only
  (see Gates). Never pasted into chat, never written into files.

## Outputs

- Placed calls with provider call IDs.
- A per-call report built **from the provider's call record**, never from
  vibes: `status`, `endedReason`, duration, `cost`, transcript, AI
  summary, and the recording URL.
- SMS delivery records (message SID + status).
- Booked appointments: the calendar event payload written, plus the
  confirmation SMS record.
- A campaign log: who was called, outcome, cost, and opt-out flags.

---

## Protocol

### 0. Preflight (every campaign, no exceptions)

1. Confirm the approval gate (see Gates): the user has approved **this**
   list, **this** script, and **this** spend envelope.
2. Scrub the list against the never-contact / opt-out list. Anyone who
   has ever said "remove me", "stop calling", or equivalent is out —
   permanently, across campaigns.
3. Verify credentials resolve from the environment/secret store. If a
   key is missing, stop and say which one; never ask the user to paste
   a key into chat.
4. Verify balance/credit and the number's daily limits before dialing
   (see Platform limits). Report the starting balance.
5. Do a **test call to the user's own number first** when the assistant,
   script, or number is new or changed. Confirm audio, opener, and the
   booking tool end-to-end before any real contact is dialed.

### 1. Outbound conversational calls (Vapi)

1. Create or update the assistant: model, voice, `firstMessage`, and a
   system prompt carrying the full script — opener, pitch, objection
   ladder, delivery/next-step explanation, and hard exits. Put per-call
   facts in **variable values** (`{{buyerName}}`, `{{company}}`,
   `{{email}}`) rather than editing the prompt per call.
2. Place calls with `POST /call/phone`: `{assistantId, phoneNumberId,
   customer: {number}, assistantOverrides: {variableValues: {...}}}`.
   Dial in small batches; watch the daily outbound cap on free numbers.
3. After each call ends, fetch `GET /call/{id}` and report from the
   record: status, `endedReason` (e.g. `customer-ended-call`,
   `silence-timed-out`, `customer-busy`, `customer-did-not-answer`),
   cost, transcript, summary, `artifact.recordingUrl`.
4. Hand the user the **recording URL** (a direct audio link). The live
   monitor `listenUrl` is a `wss://` stream — it does not play as a
   normal link in chat, so never present it as the way to listen.
5. Log every outcome in the campaign log, including $0 busy/no-answer
   calls. Update the running spend against the approved envelope after
   every batch.

Field-level detail: [references/vapi.md](references/vapi.md).

### 2. Scripted calls and SMS (Twilio)

1. Host a TwiML document (TwiML Bin, a Function, or your own webhook)
   that says the message with `<Say>` or plays a recording with
   `<Play>`.
2. Place the call from the console, a Function using
   `context.getTwilioClient()`, or the REST API:
   `Calls.create({from, to, url})`.
3. SMS: `Messages.create({from, to, body})`; record the message SID and
   poll/fetch status until `delivered` (or report the failure status
   verbatim).
4. Trial accounts can only call/message **verified numbers** — see
   Platform limits before promising any trial-account outreach.

Field-level detail: [references/twilio.md](references/twilio.md).

### 3. Inbound calls (receiving)

**Vapi:** create the receptionist assistant, then assign it to a phone
number (the number's `assistantId`). Inbound calls are answered by the
assistant with its `firstMessage` as the greeting. Enable the booking
tool (below) and an end-of-call summary webhook if you need records
pushed to your systems.

**Twilio:** point the number's Voice webhook at your endpoint (or a
TwiML Bin / Studio flow). The webhook returns TwiML: `<Gather>` for
speech/DTMF menus, `<Dial>` to forward to a human, `<Record>` for
voicemail. For a conversational AI on Twilio you supply your own
STT → LLM → TTS loop (e.g. Media Streams); Twilio itself is the pipe.

Inbound rules: answer with who you are (business + that it's an AI
assistant where required), offer a human/opt-out path, and never let an
inbound bot argue with a caller who asks to stop or be removed.

### 4. Booking during a call

The pattern is a **tool call → webhook → calendar → confirmation SMS**
loop. A complete working example lives in
[examples/booking-webhook/](examples/booking-webhook/) with a sample
receptionist prompt in
[examples/booking-receptionist-prompt.md](examples/booking-receptionist-prompt.md).

1. Define a tool on the assistant, e.g. `book_appointment`, with this
   data contract (all strings unless noted):

   ```json
   {
     "name": "Jordan Lee",
     "service": "Initial consultation",
     "date": "2026-11-20",
     "time": "14:30",
     "timezone": "America/Toronto",
     "phone": "+1 555 0100",
     "notes": "First visit; prefers afternoons"
   }
   ```

2. The assistant collects the fields conversationally, **reads the
   date/time back for confirmation**, and only then calls the tool.
3. Your webhook validates the payload, checks the slot is still free,
   and writes the calendar event (Google Calendar API event shape:
   `summary`, `start.dateTime`, `end.dateTime`, `timeZone`,
   `attendees`, `description` — provider-agnostic notes in the example).
4. The webhook returns success/failure to the assistant, which tells the
   caller the outcome truthfully — booked, or offers alternatives if
   the slot was taken.
5. Send a **confirmation SMS via Twilio** with the appointment details
   and a reschedule/cancel path. Log the event ID + message SID against
   the call record.

Never let the assistant invent availability, confirm a booking the
webhook rejected, or state a time it did not read back.

### 5. Reporting

Report per call and per campaign **from provider records only**:
outcome, ended reason, duration, cost, transcript excerpt, recording
URL, running total vs. the approved envelope, and who is left to call.
A call that reached voicemail is reported as voicemail — never dressed
up as a conversation.

---

## Gates (non-negotiable)

- **Human approval before dialing real people.** The user approves the
  exact list, script, and spend envelope for each campaign. One
  campaign's approval is not standing permission for the next.
- **Opt-out is absolute and instant.** An explicit "remove me / don't
  call again / stop" ends the call immediately with a brief
  confirmation, flags the number never-contact, and removes it from
  every future list. No persuasion ladder runs after an opt-out.
- **Never-contact lists are scrubbed before every batch**, in code, not
  by memory.
- **Keys live in secret storage.** API keys and tokens come from
  environment variables or a vault/secret manager. Never in code, never
  in the repo, never pasted into chat. If a key is exposed, roll it.
- **Spend awareness.** Know the balance and per-minute cost before
  dialing; track spend per call; stop at the user's stated floor/limit
  — except that a live conversation already in progress may finish
  naturally if the user has said so.
- **Honest representation.** The agent identifies the business it calls
  for, does not invent results, testimonials, or numbers, and does not
  claim to be human.
- **Test calls go to the user's own number** unless the user names
  another test target.

## Platform limits (observed 2026-11 — verify before relying on them)

- **Vapi free (platform-provided) numbers:** a daily outbound call cap
  applies (≈10 calls/day observed; the API refuses with "Numbers Bought
  On Vapi Have A Daily Outbound Call Limit. Import Your Own Twilio
  Numbers To Scale Without Limits."). US free numbers **cannot place
  international calls** ("Free Vapi numbers do not support international
  calls"). Importing your own Twilio number into Vapi removes both
  limits.
- **Vapi pricing shape:** ≈$0.05/min platform fee plus pass-through
  (model, voice, telephony) — observed all-in ≈$0.10–0.17/min. The
  account freezes at $0 balance.
- **Vapi API access:** the API sits behind Cloudflare; some HTTP
  clients get `403 / error code 1010`. Sending a normal browser
  `User-Agent` header fixes it.
- **Twilio trial:** calls/messages only to **verified numbers** (max 5);
  outbound trial calls begin with a short Twilio preamble and are
  time-capped; trial SMS bodies are prefixed with "Sent from your
  Twilio trial account - ". Buyer/stranger outreach requires a paid
  upgrade.
- **Caller ID** on outbound calls is the platform number used, never
  the user's personal number (unless that number is a verified caller
  ID deliberately configured).

## Honest limits of this skill

- This skill operates the platforms; it does not make the offer sell.
  Pickup rates, gatekeepers, voicemail, and IVR menus dominate cold
  outbound — expect most calls to end without a conversation, and say
  so in reports.
- Platform limits, prices, and API shapes change; the dated
  observations above must be re-verified against the live API/docs
  before a campaign depends on them.
- Booking correctness depends on the calendar behind the webhook: if
  the availability check is wrong, the assistant will confidently book
  wrong slots. Test the webhook, not just the prompt.
- Legal/telecom rules (consent, calling hours, AI-disclosure, DNC
  registries) vary by jurisdiction and are the operator's
  responsibility; this skill's gates are a floor, not legal advice.
- The skill cannot verify that a number belongs to the named person —
  it dials what the approved list says.
