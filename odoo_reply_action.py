# Odoo safe_eval action for automation 27. Secrets are not stored in this file.
if len(records) != 1 or not isinstance(payload, dict):
    raise UserError('invalid_mebel_payload')
wa = records.with_user(2)
if wa.wa_account_id.id != 9 or wa.message_type != 'inbound' or not wa.msg_uid or not wa.mail_message_id:
    raise UserError('invalid_mebel_inbound')
kind = payload.get('kind', 'reply')
if kind == 'diagnostic':
    if payload.get('status') == 'ok':
        log('MEBEL_GEMINI_TEST_OK: ' + str(payload.get('reply', ''))[:1800], level='info')
    else:
        log('MEBEL_GEMINI_TEST_FAILED: ' + str(payload.get('error', 'unknown'))[:120], level='warning')
elif kind == 'reply':
    if str(payload.get('msg_uid', '')) != wa.msg_uid:
        raise UserError('mebel_message_mismatch')
    text = payload.get('reply')
    image_reply = payload.get('customer_image', False)
    if not isinstance(image_reply, bool):
        raise UserError('invalid_mebel_image_flag')
    if not isinstance(text, str) or not text.strip() or len(text) > 1800:
        raise UserError('invalid_mebel_reply')
    if (datetime.datetime.utcnow() - wa.create_date).total_seconds() > 82800:
        raise UserError('mebel_reply_window_expired')
    wa = wa.try_lock_for_update()
    if not wa:
        raise UserError('mebel_message_busy')
    previous = env['whatsapp.message'].with_user(2).search([('wa_account_id', '=', 9), ('message_type', '=', 'outbound'), ('parent_id', '=', wa.id)], limit=1)
    if not previous or (image_reply and not wa.x_mebel_customer_image_done):
        msg = wa.mail_message_id
        if msg.model != 'discuss.channel' or not msg.res_id:
            raise UserError('invalid_mebel_channel')
        channel = env['discuss.channel'].with_user(2).browse(msg.res_id).exists()
        if not channel:
            raise UserError('mebel_channel_missing')
        sent = channel.message_post(body=text.strip(), message_type='whatsapp_message', subtype_xmlid='mail.mt_comment')
        outgoing = env['whatsapp.message'].with_user(2).search([('wa_account_id', '=', 9), ('mail_message_id', '=', sent.id), ('message_type', '=', 'outbound')], limit=1)
        if not outgoing:
            raise UserError('mebel_outbound_missing')
        outgoing.write({'parent_id': wa.id})
        log('MEBEL_GEMINI_REPLY_QUEUED inbound=%s outbound=%s' % (wa.id, outgoing.id), level='info')
    cleanup = {'x_mebel_customer_image_data': False, 'x_mebel_customer_image_mime': False,
               'x_mebel_customer_image_status': False, 'x_mebel_ai_context': False}
    if image_reply:
        cleanup['x_mebel_customer_image_done'] = True
    wa.write(cleanup)
else:
    raise UserError('invalid_mebel_operation')
