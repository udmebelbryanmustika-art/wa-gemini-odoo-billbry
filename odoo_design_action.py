# Native Odoo safe_eval action. Account 9 / company 6 / website 7 only.
# Images are existing catalogue illustrations, never claimed as completed work.
def plain_text(value):
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
    return ' '.join(''.join(chars).replace('&nbsp;', ' ').lower().split())


def design_request(text):
    for word in ['jangan kirim', 'tidak perlu gambar', 'tanpa gambar',
                 'bukti transfer', 'komplain', 'rusak', 'refund', 'retur',
                 'gambar sendiri', 'foto sendiri', 'desain sendiri', 'gambar saya',
                 'foto saya', 'desain saya', 'gambar dari saya', 'foto dari saya', 'saya kirim', 'saya punya', 'saya ada',
                 'punya gambar', 'punya foto', 'tidak ada yang cocok', 'tidak cocok',
                 'belum cocok', 'kurang cocok']:
        if word in text:
            return False
    media = False
    for word in ['gambar', 'foto', 'desain', 'referensi', 'contoh', 'katalog', 'lihat produk']:
        if word in text:
            media = True
    request = False
    for word in ['minta', 'lihat', 'kirim', 'kasih', 'boleh', 'bisa', 'ada',
                 'referensi', 'contoh', 'carikan', 'pilihan', 'rekomendasi']:
        if word in text:
            request = True
    return media and (request or len(text.split()) <= 5)


def design_products(text):
    plans = [
        (['meja makan', 'lemari', 'wardrobe', 'sofa', 'tempat tidur'], []),
        (['meja belajar'], [683, 682, 684]),
        (['meja kerja', 'desk'], [682, 683, 684]),
        (['meja laptop'], [684, 682]),
        (['meja tv'], [685, 686]),
        (['meja konsol'], [686, 685]),
        (['meja tamu', 'coffee table'], [681, 680]),
        (['meja', 'table'], [682, 683, 681]),
        (['kursi makan'], [693, 692]),
        (['kursi cafe', 'kursi kafe'], [692, 693, 691]),
        (['bangku', 'stool'], [690, 691]),
        (['kursi', 'chair'], [692, 693, 690]),
        (['rak sepatu'], [676, 677]),
        (['rak buku'], [687, 689]),
        (['rak dinding'], [688, 689]),
        (['rak tanaman'], [695, 689]),
        (['rak', 'shelf'], [687, 688, 689]),
        (['nakas', 'bedside'], [678, 679]),
        (['kabinet', 'cabinet'], [694, 678, 679]),
    ]
    for words, ids in plans:
        for word in words:
            if word in text:
                return ids
    return None


def post_design_reply(channel, wa, body, attachment=None):
    values = {'body': body, 'message_type': 'whatsapp_message',
              'subtype_xmlid': 'mail.mt_comment'}
    if attachment:
        values['attachment_ids'] = [attachment.id]
    sent = channel.message_post(**values)
    outgoing = env['whatsapp.message'].with_user(2).search([
        ('wa_account_id', '=', 9), ('mail_message_id', '=', sent.id),
        ('message_type', '=', 'outbound')])
    if not outgoing:
        raise UserError('mebel_design_outbound_missing')
    outgoing.write({'parent_id': wa.id})


W = env['whatsapp.message'].with_user(2).with_context(allowed_company_ids=[6])
P = env['product.template'].with_user(2).with_context(allowed_company_ids=[6])
for wa in records.with_user(2).with_context(allowed_company_ids=[6]):
    if (wa.wa_account_id.id != 9 or wa.message_type != 'inbound' or not wa.msg_uid
            or not wa.mail_message_id or wa.mail_message_id.model != 'discuss.channel'
            or not wa.mail_message_id.res_id or wa.x_mebel_design_options
            or not wa.create_date
            or not 0 <= (datetime.datetime.utcnow() - wa.create_date).total_seconds() < 82800):
        continue
    text = plain_text(wa.body)
    history = W.search([('wa_account_id', '=', 9), ('message_type', '=', 'inbound'),
                        ('mail_message_id.model', '=', 'discuss.channel'),
                        ('mail_message_id.res_id', '=', wa.mail_message_id.res_id),
                        ('id', '<', wa.id),
                        ('create_date', '>=', datetime.datetime.utcnow() - datetime.timedelta(hours=23))], order='id desc', limit=6)
    previous = False
    for old in history:
        if old.x_mebel_design_options and (old.x_mebel_design_options == '?' or old.x_mebel_design_options[0].isdigit()):
            previous = old
            break
    selection = 0
    for index in [1, 2, 3]:
        if text.strip(' .!') in [str(index), 'pilih ' + str(index), 'nomor ' + str(index),
                                 'yang ' + str(index), 'pilihan ' + str(index)]:
            selection = index
    selected = False
    products = design_products(text)
    requested = design_request(text)
    if previous and previous.x_mebel_design_options == '?' and products is not None:
        requested = True
    if selection and previous and previous.x_mebel_design_options[0].isdigit():
        ids = previous.x_mebel_design_options.split(',')
        if selection <= len(ids):
            selected = P.browse(int(ids[selection - 1])).exists()
            requested = True
    if not requested:
        continue
    if products is None and not selected:
        for old in history[:3]:
            products = design_products(plain_text(old.body))
            if products is not None:
                break
    candidates = []
    for product_id in products or []:
        p = P.browse(product_id).exists()
        if (p and p.company_id.id == 6 and p.website_id.id in [False, 7]
                and p.website_published and p.image_1024 and p.image_1024.size < 3000000
                and str(p.website_url or '').startswith('/shop/')):
            candidates.append(p)
    if selected and (selected.company_id.id != 6 or not selected.website_published
                     or selected.website_id.id not in [False, 7]):
        selected = False
    if env.context.get('mebel_design_dry_run'):
        log('MEBEL_DESIGN_DRY_RUN inbound=%s products=%s selected=%s' %
            (wa.id, [p.id for p in candidates], selected.id if selected else False), level='info')
        continue
    wa = wa.try_lock_for_update()
    if not wa or wa.x_mebel_design_options:
        continue
    channel = env['discuss.channel'].with_user(2).browse(wa.mail_message_id.res_id).exists()
    if not channel:
        continue
    if selected:
        post_design_reply(channel, wa, 'Baik, Kak, pilihannya %s. Desainnya masih berupa referensi; ukuran, bahan, dan finishing final dikonfirmasi bersama admin. Untuk disesuaikan dengan ruang Kakak, ukuran yang dibutuhkan berapa?' % selected.name)
        wa.write({'x_mebel_design_options': 'selected:' + str(selected.id)})
        lead = wa.x_mebel_crm_lead_id
        if lead and lead.company_id.id == 6:
            lead.with_user(2).message_post(body='Pilihan referensi desain WhatsApp: %s. Belum merupakan pesanan atau spesifikasi final.' % selected.name, subtype_xmlid='mail.mt_note')
        continue
    if products is None:
        post_design_reply(channel, wa, 'Boleh, Kak. Saya bantu pilihkan ilustrasi desain untuk referensi. Kakak ingin melihat meja, kursi, rak, nakas, atau kabinet?')
        wa.write({'x_mebel_design_options': '?'})
        continue
    if not candidates:
        post_design_reply(channel, wa, 'Untuk model itu, ilustrasi yang sesuai belum tersedia di katalog kami, Kak. Boleh kirim foto referensi atau jelaskan bentuk dan gaya yang diinginkan? Nanti spesifikasi finalnya perlu dikonfirmasi admin.')
        wa.write({'x_mebel_design_options': 'unavailable'})
        continue
    sent_ids = []
    for p in candidates[:3]:
        attachment = env['ir.attachment'].with_user(2).create({
            'name': 'Referensi desain - %s' % p.name,
            'raw': p.image_1024, 'res_model': 'discuss.channel', 'res_id': channel.id})
        if attachment.mimetype not in ['image/jpeg', 'image/png']:
            continue
        caption = 'Referensi %s — %s.\nIlustrasi desain katalog, bukan foto hasil produksi atau spesifikasi final.\nSumber: https://mebel.billbry.id%s' % (len(sent_ids) + 1, p.name, p.website_url)
        post_design_reply(channel, wa, caption, attachment)
        sent_ids.append(p.id)
    if sent_ids:
        post_design_reply(channel, wa, 'Dari referensi ini, model nomor berapa yang paling cocok, Kak? Sebutkan bagian bentuk, warna, atau penyimpanan yang ingin disesuaikan. Harga dan pengerjaan dikonfirmasi admin setelah spesifikasi disepakati.')
        wa.write({'x_mebel_design_options': ','.join(str(i) for i in sent_ids)})
        log('MEBEL_DESIGNS_QUEUED inbound=%s images=%s company=6' % (wa.id, len(sent_ids)), level='info')
