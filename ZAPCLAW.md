# Citra through ZapClaw Coexistence

Status: prepared; automation defaults OFF. Existing phone pairing is retained.

- Number: +6285187219372. ZapClaw number ID: 1351353461401080.
- Webhook: `/webhooks/zapclaw`, HMAC-SHA256 over exact raw bytes.
- Mandatory secrets: ZAPCLAW_WEBHOOK_SECRET, ZAPCLAW_API_KEY; Upstash KV_REST_API_URL and KV_REST_API_TOKEN.
- Enable only after verifying the public endpoint and successful queue deployment: ZAPCLAW_ENABLED=true.
- Subscribe to inbound messages, statuses, and WhatsApp Business app echoes in ZapClaw.
- `citra_worker` is a private Vercel Queue subscriber discovered through pyproject.toml.
- Ingress acknowledges only after durable queue publish. Queue failure returns503 for provider retry.
- Redis is durable with eviction OFF. Sent/attempted dedup keys live7days; recent12 conversation pairs expire after7days. Queue payloads retain for1hour. No customer content or API secrets in logs.
- New inbound text must be at most5minutes old. Historical and imported messages do not generate replies.
- Customer `Hubungi Admin`, incoming media, or phone/Web echo pauses AI for that conversation for24hours. Media is left for admin; this initial route does not claim to inspect images.
- Phone echo is checked again atomically after AI generation. A send already in progress when admin replies cannot be recalled. Windows desktop/WearOS may not provide echoes; use the Business phone app for reliable handoff.
- An outgoing API call is attempted once. Timeout,202, or refusal leaves the conversation paused for admin. Never automatically retry an ambiguous send after provider idempotency expires.
- Gemini failures before send may retry via Queue; after four failures the conversation is paused. Redis failures fail closed.
- When enabled, old raw Meta `/webhook` replies are disabled to prevent two send paths. Odoo blueprint is unchanged; this route does not sync new ZapClaw chats into Odoo CRM.
- Stop: set ZAPCLAW_ENABLED=false and redeploy; pause webhook delivery in ZapClaw to retain events during maintenance.

## Verification

Install dev-only `pytest` and `fakeredis[lua]`, then `python -m pytest -q`.
Tests cover signed ingress, number scope, expired/history messages, durable enqueue failure, duplicate delivery, handoff during generation, unknown sends, Redis outage, and Gemini recovery. The private Queue subscriber must also import successfully and appear in deployment output before activating.

## Current account blocker observed 2026-11-05

ZapClaw reports Meta account payment-method error and inability to send. Meta business settings show no payment method for WABA1111731908174978. Owner Billbry Mustika Karya Karya was subsequently assigned full access with explicit owner approval; WhatsApp Manager now opens and confirms the number Connected with High quality. Meta says free conversations can be customer-initiated and records one successful free service reply. Verify a new customer-initiated reply before declaring automation functional. Do not attach a card or expand account permissions without owner authorization. A past successful onboarding send is not proof the current restriction is cleared.
