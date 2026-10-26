# Native automation 28 guard, account 9 / company 6 only.
# Serialize private image bytes to the existing authenticated bridge; no public URLs.
def vision_plain(value):
    chars = []
    hidden = False
    for ch in str(value or ''):
        if ch == '<':
            hidden = True
            chars.append(' ')
        elif ch == '>':
            hidden = False
        elif not hidden:
            chars.append(ch)
    return ' '.join(''.join(chars).replace('&nbsp;', ' ').split())


W = env['whatsapp.message'].with_user(2).with_context(allowed_company_ids=[6])
for wa in records.with_user(2).with_context(allowed_company_ids=[6]):
    if (wa.wa_account_id.id != 9 or wa.message_type != 'inbound' or not wa.msg_uid
            or not wa.mail_message_id or wa.mail_message_id.model != 'discuss.channel'
            or not wa.mail_message_id.res_id or not wa.create_date
            or not 0 <= (datetime.datetime.utcnow() - wa.create_date).total_seconds() < 82800):
        continue
    domain = [('wa_account_id', '=', 9), ('parent_id', '=', wa.id), ('message_type', '=', 'outbound')]
    replied = W.search(domain, limit=1)
    attachments = wa.mail_message_id.attachment_ids
    if replied and (not attachments or wa.x_mebel_customer_image_done):
        continue
    if not attachments and not env.context.get('mebel_vision_dry_run'):
        env['ir.actions.server'].with_user(2).browse(1795).with_context(active_model='whatsapp.message', active_id=wa.id, active_ids=wa.ids).run()
        if W.search(domain, limit=1):
            continue
    values = {'x_mebel_customer_image_data': False, 'x_mebel_customer_image_mime': False,
              'x_mebel_customer_image_status': False, 'x_mebel_ai_context': ''}
    if attachments:
        photo = False
        for attachment in attachments:
            if attachment.mimetype in ['image/jpeg', 'image/png', 'image/webp']:
                photo = attachment
                break
        if not photo:
            values['x_mebel_customer_image_status'] = 'unsupported'
        elif not photo.raw or not photo.raw.size:
            continue
        elif photo.raw.size > 1500000:
            values['x_mebel_customer_image_status'] = 'oversize'
        else:
            values['x_mebel_customer_image_data'] = photo.raw.to_base64()
            values['x_mebel_customer_image_mime'] = photo.mimetype
            values['x_mebel_customer_image_status'] = 'image'
    history = W.search([('wa_account_id', '=', 9),
                        ('mail_message_id.model', '=', 'discuss.channel'),
                        ('mail_message_id.res_id', '=', wa.mail_message_id.res_id),
                        ('id', '<', wa.id),
                        ('create_date', '>=', datetime.datetime.utcnow() - datetime.timedelta(hours=23))],
                       order='id desc', limit=40)
    # Keep customer facts from earlier turns, plus the latest dialogue. Long
    # assistant replies must not crowd out an address or agreed specification.
    lines = []
    customer_lines = []
    for old in history.sorted('id'):
        body = vision_plain(old.body)[:500 if old.message_type == 'inbound' else 220]
        if body:
            role = 'Pelanggan' if old.message_type == 'inbound' else 'Citra'
            line = role + ': ' + body
            lines.append(line)
            if old.message_type == 'inbound':
                customer_lines.append(line)
    # Whole lines only; do not truncate the newest correction halfway through.
    retained = []
    used = 0
    for line in customer_lines[::-1]:
        if used + len(line) + 1 <= 2800:
            retained.append(line)
            used += len(line) + 1
    recent = []
    used = 0
    for line in lines[::-1]:
        if used + len(line) + 1 > 2900:
            break
        recent.append(line)
        used += len(line) + 1
    if lines:
        values['x_mebel_ai_context'] = ('Detail dari pesan pelanggan (urut waktu):\n'
            + '\n'.join(retained[::-1]) + '\nPercakapan terbaru (urut waktu):\n'
            + '\n'.join(recent[::-1]))
    if env.context.get('mebel_vision_dry_run'):
        log('MEBEL_VISION_DRY_RUN inbound=%s image=%s context_chars=%s' %
            (wa.id, values['x_mebel_customer_image_status'] or 'none', len(values['x_mebel_ai_context'])), level='info')
        continue
    wa.write(values)
    env['ir.actions.server'].with_user(2).browse(1780).with_context(active_model='whatsapp.message', active_id=wa.id, active_ids=wa.ids).run()
