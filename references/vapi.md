# Vapi reference — endpoints, fields, and behaviours

Generic reference for building with the Vapi API (`https://api.vapi.ai`).
No account data. Observed 2026-11; re-verify against current Vapi docs.

## Auth

- Header: `Authorization: Bearer <VAPI_PRIVATE_API_KEY>` — use the
  **private** key for server-side API calls (the public key is for web
  SDKs).
- Store the key in an environment variable or secret manager
  (`VAPI_API_KEY`). Never commit it.
- **Cloudflare gotcha:** some HTTP clients (e.g. Python `urllib`
  defaults) receive `403` with Cloudflare `error code: 1010`. Send a
  normal browser `User-Agent` header (plus `Accept: application/json`)
  and the same key works.

## Phone numbers

- `GET /phone-number` — list numbers on the account. Each has an `id`,
  `number` (E.164), `provider` (`vapi` for free platform numbers, or
  `twilio`/`byo-phone-number` for imported), and optionally an
  `assistantId` (the assistant that answers inbound calls).
- Free platform numbers: one US number is typically included. They carry
  the daily outbound cap and the no-international-calls restriction
  (see SKILL.md → Platform limits).
- Importing a Twilio number (BYO) removes the free-number limits; calls
  then bill through your Twilio account plus Vapi fees.

## Assistants

- `POST /assistant` — create. Core shape:

  ```json
  {
    "name": "Receptionist",
    "firstMessage": "Hi, thanks for calling — how can I help?",
    "model": {
      "provider": "openai",
      "model": "gpt-4o-mini",
      "messages": [{"role": "system", "content": "<full script/prompt>"}],
      "tools": [ { "type": "function", "function": { "name": "book_appointment", "...": "..." } } ]
    },
    "voice": {"provider": "vapi", "voiceId": "Elliot"},
    "server": {"url": "https://your-webhook.example.com/vapi"}
  }
  ```

- `PATCH /assistant/{id}` — update any field (e.g. a revised script).
  The change applies to the next call; in-flight calls keep the old
  config.
- `GET /assistant/{id}` — read current config.
- **Variables:** write `{{variableName}}` placeholders in `firstMessage`
  and the system prompt; supply values per call via
  `assistantOverrides.variableValues`. This is how one assistant serves
  a whole call list.
- **Tools:** function tools are declared on the model; when the model
  calls one, Vapi POSTs to your `server.url` and speaks the returned
  result. See `examples/booking-webhook/` for the booking contract.

## Placing calls

- `POST /call/phone`:

  ```json
  {
    "assistantId": "<assistant id>",
    "phoneNumberId": "<number id>",
    "customer": {"number": "+15550100"},
    "assistantOverrides": {
      "variableValues": {"firstName": "Jordan", "company": "Example Co"}
    }
  }
  ```

  Returns the call object with `id` and `status` (`queued` →
  `in-progress` → `ended`).

- Known refusal messages (verbatim, treat as hard stops):
  - `"Couldn't start call. Free Vapi numbers do not support international calls."`
  - `"Couldn't Start Call. Numbers Bought On Vapi Have A Daily Outbound Call Limit. Import Your Own Twilio Numbers To Scale Without Limits."`

## Call records

- `GET /call/{id}` — the source of truth for reporting:
  - `status`, `endedReason` (`customer-ended-call`,
    `assistant-ended-call`, `silence-timed-out`, `customer-busy`,
    `customer-did-not-answer`, `voicemail`, …)
  - `cost` (USD total), `costBreakdown`
  - `startedAt` / `endedAt`
  - `artifact.transcript`, `artifact.recordingUrl` (direct audio file —
    this is the link to give the user)
  - `analysis.summary`, `analysis.successEvaluation`
  - `monitor.listenUrl` — a `wss://` live stream; useful for programmatic
    monitoring, **not** a playable link in chat.
- Calls are recorded by default; transcript + AI summary are generated
  after the call ends (allow a few seconds before fetching).

## Inbound

- Set the number's `assistantId` (at creation or via
  `PATCH /phone-number/{id}`) and inbound calls are answered by that
  assistant. The assistant's `firstMessage` is the greeting.
- End-of-call reports can be pushed to your `server.url` webhook
  (`end-of-call-report` message type) for logging/CRM writes.

## Costs (shape, observed 2026-11)

- Platform fee ≈ $0.05/min + pass-through for LLM, voice, and
  telephony; observed all-in ≈ $0.10–0.17/min for a mini-model +
  platform voice setup. Balance hitting $0 freezes calling.
