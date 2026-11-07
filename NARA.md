# Nara — follow-up preparation

Status: OFF by default. The only supported optional mode is `NARA_MODE=preview`.
There is no live sending mode, no template-send call and no public Nara endpoint.
Do not enable preview on production until the owner approves its consent notice.

## Prepared flow

1. In preview only, Citra appends an informed permission notice once per retained conversation. The notice explicitly says Nara is in preparation and follow-ups are not being sent automatically.
2. Only `SETUJU FOLLOW UP` after successful delivery of the current notice grants permission. Casual agreement, historic contacts and existing chat history do not count as permission. The record includes notice/version, consent message ID and timestamp, or revocation.
3. Following a successful Citra reply, a private Vercel Queue can schedule draft preparation at least two hours after the latest customer message, during Monday–Saturday08:00–16:00 Asia/Jakarta. A task that cannot fit within24hours is skipped. At most one draft per conversation per7days.
4. Before generating and again atomically before saving, state checks stop outdated jobs after a new customer reply, STOP/rejection, phone admin reply, handoff, order-completion/payment/complaint indicators, or expired permission/window. Redis/queue failures do not send anything.
5. Nara uses the recent conversation to prepare one short friendly draft without prices, discounts, production promises or pressure. Drafts are never sent; admin must review them. Consent metadata and drafts expire after7days without renewal. No phone number is added to the delayed queue payload.

This is a prepared implementation, not proof of new customer permissions or order status in CRM. There is no Odoo order/consent sync or admin draft viewer yet. Failure to publish a draft job is logged for investigation and does not affect the successful Citra reply. In-flight admin actions cannot recall a message already sent by Citra.

## Indonesian Meta template draft

See `templates/nara_followup_konsultasi_id.json`: category MARKETING, language id, no variables or price claims. It is LOCAL_DRAFT_NOT_SUBMITTED.

ZapClaw's Create Template UI currently offers only Portuguese(BR), English(US) and Spanish. The active Facebook browser session returns business_access for Mebel business1589837741640805. Therefore no Indonesian template has been submitted. Meta payment-method warning for business-initiated messages is unresolved. Sending beyond24hours must wait for the correct account, an approved template, eligible recipients with permission, and payment/cost review.

## Verification and activation boundary

Run `python -m pytest -q`. Tests include consent evidence, revocation/replay, scheduling, business hours, changed conversations, human handoff, expiry, duplicate suppression and STOP during generation; a mocked HTTP boundary proves preview draft creation does not send.

Before any live follow-up implementation: owner approves timing/frequency/message content/recipient scope; build an admin review and consent-status interface, sync confirmed order outcomes, verify actual opt-in/opt-out, resolve Meta prerequisites and test only an approved test recipient. Activation must be a separate explicit step. This preparation does not add paid plans or change credentials.
