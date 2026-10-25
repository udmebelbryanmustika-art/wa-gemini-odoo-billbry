# Automation 28 guard: native design replies first, Gemini for other requests.
W = env['whatsapp.message'].with_user(2).with_context(allowed_company_ids=[6])
for wa in records.with_user(2).with_context(allowed_company_ids=[6]):
    if wa.wa_account_id.id == 9 and wa.message_type == 'inbound' and wa.msg_uid and wa.mail_message_id:
        domain = [('wa_account_id', '=', 9), ('parent_id', '=', wa.id), ('message_type', '=', 'outbound')]
        replied = W.search(domain, limit=1)
        if not replied:
            env['ir.actions.server'].with_user(2).browse(1795).with_context(active_model='whatsapp.message', active_id=wa.id, active_ids=wa.ids).run()
            replied = W.search(domain, limit=1)
            if not replied:
                env['ir.actions.server'].with_user(2).browse(1780).with_context(active_model='whatsapp.message', active_id=wa.id, active_ids=wa.ids).run()
