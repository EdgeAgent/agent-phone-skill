# Twilio reference — calls, SMS, TwiML, trial rules

Generic reference for building with Twilio. No account data. Observed
2026-11; re-verify against current Twilio docs.

## Auth & credentials

- API calls authenticate with **Account SID + Auth Token** (two
  secrets, used as HTTP Basic auth), or an API Key SID/Secret pair.
- Both halves live in a secret manager / environment
  (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`). A single-secret vault
  deposit cannot hold the pair — store them as separate entries.
- Console login is separate from API credentials; never conflate them.

## Numbers

- Buy numbers in Console → Phone Numbers (or the API). Local numbers
  are roughly $1.15/mo (US/CA, observed) plus usage.
- **Verified Caller IDs** (trial): outbound trial calls may only go to
  numbers you have verified (Console → Phone Numbers → Verified Caller
  IDs; verification is an SMS/voice code to that handset). Max 5 on
  trial.

## Trial account rules (hard limits)

- Calls and messages **only to verified numbers**.
- Outbound trial calls start with a short Twilio preamble ("This is a
  trial account…") audible to the callee, and are time-capped
  (~10 minutes).
- Trial SMS bodies are prefixed: `Sent from your Twilio trial account - `.
- Trial credit is a small starting balance (≈$10 observed). Stranger
  outreach requires upgrading to a paid account.

## Placing a scripted call

A call needs TwiML telling Twilio what to say:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="Polly.Joanna">Hello, this is a reminder of your appointment tomorrow at 2:30 PM.</Say>
</Response>
```

Host it as a **TwiML Bin** (Console → TwiML Bins), a **Function**, or
your own HTTPS webhook. Then place the call:

- REST: `POST /2010-04-01/Accounts/{Sid}/Calls.json` with `From`,
  `To`, `Url` (the TwiML URL).
- From a Twilio Function (no credentials handling — the runtime injects
  them):

  ```js
  const client = context.getTwilioClient();
  await client.calls.create({
    from: "+15550100",            // your Twilio number
    to: "+15550199",              // destination
    url: "https://handler.twilio.com/twiml/<your-bin-sid>"
  });
  ```

- Call record: fetch the Call SID for `status` (`completed`, `busy`,
  `no-answer`, `failed`), `duration`, and `price`.

## SMS

- REST: `POST /2010-04-01/Accounts/{Sid}/Messages.json` with `From`,
  `To`, `Body`.
- Record the returned Message SID; fetch it later for `status`
  (`queued` → `sent` → `delivered`, or `undelivered`/`failed` with an
  error code). Report delivery from the record, not from the send
  returning 201.
- Inbound SMS: set the number's Messaging webhook to receive `From`,
  `To`, `Body` POSTs; reply by returning TwiML `<Response><Message>…`.

## Inbound voice routing

Set the number's Voice webhook URL. Twilio POSTs the call; your TwiML
response routes it:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech dtmf" numDigits="1" action="/menu">
    <Say>Press 1 to book, 2 to reach a person, or just tell me what you need.</Say>
  </Gather>
  <Dial>+15550199</Dial>   <!-- fall through to a human -->
</Response>
```

- `<Gather>` — collect speech/DTMF. `<Dial>` — forward/bridge.
  `<Record>` — voicemail. `<Say>`/`<Play>` — speak/play.
- Conversational AI on Twilio = your own loop: **Media Streams**
  (WebSocket audio) → STT → LLM → TTS → back. Twilio provides the pipe
  and the number, not the brain. (For a managed brain, that is the Vapi
  lane — including Vapi running on top of an imported Twilio number.)

## Costs (shape, observed 2026-11)

- US/CA local number ≈ $1.15/mo; outbound voice ≈ $0.014/min (US);
  SMS ≈ $0.008–0.017/message depending on route. Trial credit covers
  testing only.
