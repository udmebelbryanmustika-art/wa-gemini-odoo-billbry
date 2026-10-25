# Mebel WhatsApp AI bridge

Status: implementation tested with mocks; live AI generation and delivery are not yet verified.
Meta's existing callback remains Odoo `/whatsapp/webhook`. Odoo is the only WhatsApp sender.

1. Odoo automation 27 receives replies. Its fixed target expression is
   `model.browse(int(payload.get('inbound_id') or 0)).exists()` on `whatsapp.message`.
   Use `odoo_reply_action.py` as its Execute Code action.
2. After authorization, save the generated confidential callback URL as the **secret**
   production environment variable `ODOO_REPLY_WEBHOOK_URL` in this Vercel project.
   Use the `https://mebel.billbry.id/web/hook/...` URL. Never commit the value.
3. Configure an Odoo Send Webhook Notification action to POST to this project's
   `/odoo/inbound`, using HTTP Basic username `mebel` and the callback URL's final
   opaque path component as the password. The Requests URL userinfo form supplies
   Basic authentication; credentials should not appear in the request path or query.
4. Send only `_model`, `_id`, `wa_account_id`, `message_type`, `msg_uid`,
   `create_date`, and `body`. These are native Odoo payload names, verified in its UI.
   Recipient phone numbers and profile names are not needed by Gemini.
5. Use `/odoo/ai-test` with the same authentication for a fixed synthetic question.
   It writes `MEBEL_GEMINI_TEST_OK` or `MEBEL_GEMINI_TEST_FAILED` through callback 27;
   it does not send WhatsApp messages. A local mocked test passing is not live AI proof.
6. Only after the synthetic test succeeds, attach the outbound action to a new
   automation scoped to account 9, inbound messages, and non-empty message UID and
   mail message. Watch creation and changes of mail message and UID. Restrict to
   messages created after activation. Do not replay historical customer messages.
7. Ask the owner to send a new test. Verify one inbound, one linked outbound, and
   Meta delivery status in Odoo. Do not claim delivery from HTTP callback success.

The incoming callback rejects other accounts and arbitrary recipient changes, locks
the original inbound before posting, and refuses another outbound linked to it.
Both sides enforce a conservative 23-hour window. The worker does not use the Meta
access token or an Odoo administrator API key. Gemini receives only the message text
and fixed business instructions. Callback URLs and secrets are never logged in code.

No durable retry queue is included. A failed Odoo notification must be reviewed and
retried deliberately; generation or callback failure never reports a sent AI reply.
Pause the outbound automation for rollback; inbound WhatsApp reception stays in Odoo.
