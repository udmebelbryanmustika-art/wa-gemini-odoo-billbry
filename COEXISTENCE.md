# Coexistence migration preparation — Mebel only

## Verified on 27 October 2026

- ZapClaw account signed in, Free plan (0 / 500 messages); no number connected.
- The connection wizard requires an active WhatsApp Business app number that
  is not connected to another provider. The current Mebel number is API-only.
- The owner confirms the SIM can receive normal SMS/calls for verification.
- No deregistration, provider permission grant, webhook activation or credential
  changes have been performed.

## Code prepared, not activated

`coexistence_events.py` verifies ZapClaw's raw-body HMAC signature, pins the
connection's Phone Number ID and Mebel number, and normalizes customer messages
and phone-sent echoes. A phone echo produces a handoff requirement rather than
an AI prompt, including when an admin sends media. Username-only identities are
preserved. There is no network access, sending, HTTP route or production import.

This is a parsing component, **not an operational integration**. Before any
cutover, the remaining implementation must provide:

1. Durable event storage, message-ID deduplication and atomic per-conversation
   handoff state. A replay must not send a second reply or reopen an old handoff.
2. An authenticated, company-6/account-9-scoped Odoo receiver that records both
   directions in the correct customer channel without triggering a second send.
3. A sender strategy compatible with Odoo Online. The current Odoo callback posts
   a native WhatsApp message; merely forwarding ZapClaw events cannot replace it.
   ZapClaw documents a Chatwoot proxy, not a validated Odoo Online integration.
4. Media, delivery/error statuses, account alerts, reply-window checks and a
   serialized queue that checks for admin takeover again immediately before send.
5. A live test on a non-production number, including simultaneous admin/AI
   handling, duplicate events and recovery after a failed callback.

Do not point the provider at an unimplemented endpoint: returning HTTP 200 before
durably accepting an event would acknowledge and potentially lose the message.
Do not install this parser as a standalone webhook and claim sync is complete.

## Cutover gate

Only after those checks, arrange a downtime window with the owner. Record current
Meta/Odoo identifiers and protected settings for recovery; do not put credentials
in this repository. Deregistration must not delete the WhatsApp account, business
portfolio or chat backup. The owner registers the same number in the phone app,
enters verification/PIN privately, restores any available backup, and uses the app
normally. Coexistence eligibility and the waiting period are controlled by Meta;
same-day approval is not guaranteed. Returning to API-only would end phone-app use.

On approved onboarding, verify the new connection's Phone Number ID instead of
assuming the old identifier survived. Request provider access explicitly at the
actual Meta consent screen, restrict it to Mebel, and opt into phone-message
echoes. Historical imports must never trigger fresh automated replies.

## Free-plan constraint

ZapClaw publishes 500 combined incoming/API-outgoing messages per month. On
reaching the limit, API sending and webhook delivery pause; the phone app keeps
receiving messages. Provider subscription is free within that limit; Meta/API
and AI usage can still have costs. Do not auto-upgrade or fund a wallet.

Sources checked:
- https://zapclaw.app/docs.html (signature, account scope, echoes, proxy)
- https://zapclaw.app/pricing.html (free allowance and pause behavior)

Rollback must restore one verified inbound path and one sender. Keep the existing
production bridge unchanged until a replacement has been validated end to end.
