import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

CODE = compile(Path(__file__).with_name('odoo_vision_inbound_action.py').read_text(),
               'odoo_vision_inbound_action.py', 'exec')


class Environment(dict):
    context = {}

    def ref(self, name):
        return SimpleNamespace(id=1)


class VisionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.body = 'Meja custom?'
        self.wa.id = 500
        self.wa.ids = [500]
        self.wa.wa_account_id.id = 9
        self.wa.message_type = 'inbound'
        self.wa.msg_uid = 'test-only'
        self.wa.mail_message_id.model = 'discuss.channel'
        self.wa.mail_message_id.res_id = 20
        self.wa.mail_message_id.attachment_ids = []
        self.wa.create_date = datetime.datetime.utcnow()
        self.wa.x_mebel_customer_image_done = False
        self.records = MagicMock()
        self.records.with_user.return_value.with_context.return_value = [self.wa]
        self.messages = MagicMock()
        self.messages.with_user.return_value.with_context.return_value = self.messages
        self.replied = False
        self.history = MagicMock()
        self.history.sorted.return_value = []
        self.messages.search.side_effect = lambda domain, **kw: (
            self.replied if any(x[0] == 'parent_id' for x in domain) else self.history)
        self.actions = MagicMock()
        self.actions.with_user.return_value = self.actions
        self.design = MagicMock()
        self.design.with_context.return_value = self.design
        self.bridge = MagicMock()
        self.bridge.with_context.return_value = self.bridge
        self.actions.browse.side_effect = lambda aid: {1795: self.design, 1780: self.bridge}[aid]
        self.env = Environment({'whatsapp.message': self.messages, 'ir.actions.server': self.actions})
        self.env.context = {}
        self.notes = MagicMock()
        self.notes.with_user.return_value = self.notes
        self.notes.search.return_value = False
        self.env['mail.message'] = self.notes
        self.channels = MagicMock()
        self.channels.with_user.return_value = self.channels
        self.channel = self.channels.browse.return_value.exists.return_value
        self.channel.try_lock_for_update.return_value = self.channel
        self.env['discuss.channel'] = self.channels
        self.wa.wa_account_id.notify_user_ids.partner_id.ids = [12]
        self.photo = SimpleNamespace(mimetype='image/png', raw=SimpleNamespace(
            size=123, to_base64=MagicMock(return_value='test-only-image')))

    def run_action(self):
        exec(CODE, {'env': self.env, 'records': self.records, 'datetime': datetime,
                    'log': MagicMock(), 'UserError': RuntimeError})

    def test_admin_request_keeps_context_notifies_existing_admin_and_pauses(self):
        self.wa.body = 'hubungi admin'
        self.history.sorted.return_value = [
            SimpleNamespace(body='Meja makan 6 kursi jati walnut. Siman Ponorogo', message_type='inbound')]
        outgoing = MagicMock()
        self.messages.search.side_effect = lambda domain, **kw: (
            self.history if any(x[0] == 'create_date' for x in domain) else
            outgoing if any(x[0] == 'mail_message_id' for x in domain) else False)
        self.run_action()
        note, acknowledgement = self.channel.message_post.call_args_list
        self.assertIn('MEBEL_HANDOFF_OPEN', note.kwargs['body'])
        self.assertIn('Siman Ponorogo', note.kwargs['body'])
        self.assertEqual(note.kwargs['partner_ids'], [12])
        self.assertEqual(note.kwargs['message_type'], 'comment')
        self.assertIn('Tidak perlu mengulang', acknowledgement.kwargs['body'])
        self.design.run.assert_not_called()
        self.bridge.run.assert_not_called()
        outgoing.write.assert_called_once_with({'parent_id': 500})

    def test_paused_conversation_does_not_call_ai_or_send_catalogue(self):
        self.notes.search.return_value = SimpleNamespace(body='MEBEL_HANDOFF_OPEN inbound=499')
        self.run_action()
        self.bridge.run.assert_not_called()
        self.design.run.assert_not_called()
        self.channel.message_post.assert_not_called()

    def test_duplicate_admin_request_does_not_notify_again(self):
        self.wa.body = 'hubungi admin'
        self.notes.search.return_value = SimpleNamespace(body='MEBEL_HANDOFF_OPEN inbound=499')
        self.messages.search.side_effect = lambda domain, **kw: (
            self.history if any(x[0] == 'create_date' for x in domain) else
            MagicMock() if any(x[0] == 'mail_message_id' for x in domain) else False)
        self.run_action()
        self.channel.message_post.assert_called_once()
        self.assertEqual(self.channel.message_post.call_args.kwargs['message_type'], 'whatsapp_message')

    def test_resume_is_explicit_and_records_resume_state(self):
        self.wa.body = 'lanjut citra'
        self.notes.search.return_value = SimpleNamespace(body='MEBEL_HANDOFF_OPEN inbound=499')
        self.messages.search.side_effect = lambda domain, **kw: (
            self.history if any(x[0] == 'create_date' for x in domain) else
            MagicMock() if any(x[0] == 'mail_message_id' for x in domain) else False)
        self.run_action()
        self.assertIn('MEBEL_HANDOFF_RESUMED', self.channel.message_post.call_args_list[0].kwargs['body'])

    def test_photo_bypasses_catalog_and_exports_only_inline_bytes(self):
        self.wa.mail_message_id.attachment_ids = [self.photo]
        self.run_action()
        self.design.run.assert_not_called()
        self.bridge.run.assert_called_once()
        values = self.wa.write.call_args.args[0]
        self.assertEqual(values['x_mebel_customer_image_data'], 'test-only-image')
        self.assertEqual(values['x_mebel_customer_image_mime'], 'image/png')
        self.assertEqual(values['x_mebel_customer_image_status'], 'image')

    def test_recent_context_is_scoped_to_the_same_account_and_channel(self):
        self.history.sorted.return_value = [
            SimpleNamespace(body='<p>Meja dengan laci</p>', message_type='outbound'),
            SimpleNamespace(body='<p>120 x 60 cm</p>', message_type='inbound')]
        self.run_action()
        self.assertIn('Citra: Meja dengan laci\nPelanggan: 120 x 60 cm',
                      self.wa.write.call_args.args[0]['x_mebel_ai_context'])
        history_domain = self.messages.search.call_args.args[0]
        self.assertIn(('wa_account_id', '=', 9), history_domain)
        self.assertIn(('mail_message_id.res_id', '=', 20), history_domain)

    def test_address_survives_more_than_six_messages_and_long_sales_replies(self):
        self.history.sorted.return_value = [
            SimpleNamespace(body='Kirim ke Siman Ponorogo', message_type='inbound'),
            *[SimpleNamespace(body='Usulan meja makan ' * 60, message_type='outbound')
              for _ in range(12)],
            SimpleNamespace(body='sesuai standar saja', message_type='inbound')]
        self.run_action()
        context = self.wa.write.call_args.args[0]['x_mebel_ai_context']
        self.assertIn('Kirim ke Siman Ponorogo', context)
        self.assertIn('sesuai standar saja', context)
        self.assertLessEqual(len(context), 6000)
        self.assertEqual(self.messages.search.call_args.kwargs['limit'], 40)

    def test_newest_customer_correction_survives_full_context_budget(self):
        self.history.sorted.return_value = [
            *[SimpleNamespace(body='Deskripsi furnitur ' * 40, message_type='inbound')
              for _ in range(39)],
            SimpleNamespace(body='Koreksi alamat: Siman Ponorogo', message_type='inbound')]
        self.run_action()
        context = self.wa.write.call_args.args[0]['x_mebel_ai_context']
        self.assertIn('Koreksi alamat: Siman Ponorogo', context)
        self.assertLessEqual(len(context), 6000)

    def test_delayed_photo_can_be_processed_after_text_reply(self):
        self.replied = True
        self.wa.mail_message_id.attachment_ids = [self.photo]
        self.run_action()
        self.bridge.run.assert_called_once()

    def test_processed_photo_and_other_accounts_are_not_replayed(self):
        self.replied = True
        self.wa.mail_message_id.attachment_ids = [self.photo]
        self.wa.x_mebel_customer_image_done = True
        self.run_action()
        self.bridge.run.assert_not_called()
        self.wa.wa_account_id.id = 3
        self.run_action()
        self.wa.write.assert_not_called()

    def test_large_image_requests_resend_without_exporting_bytes(self):
        self.photo.raw.size = 1500001
        self.wa.mail_message_id.attachment_ids = [self.photo]
        self.run_action()
        self.photo.raw.to_base64.assert_not_called()
        self.assertEqual(self.wa.write.call_args.args[0]['x_mebel_customer_image_status'], 'oversize')
        self.assertFalse(self.wa.write.call_args.args[0]['x_mebel_customer_image_data'])

    def test_unsupported_document_is_not_claimed_as_analyzed(self):
        self.photo.mimetype = 'application/pdf'
        self.wa.mail_message_id.attachment_ids = [self.photo]
        self.run_action()
        self.photo.raw.to_base64.assert_not_called()
        self.assertEqual(self.wa.write.call_args.args[0]['x_mebel_customer_image_status'], 'unsupported')

    def test_photo_still_downloading_is_left_for_recovery(self):
        self.photo.raw.size = 0
        self.wa.mail_message_id.attachment_ids = [self.photo]
        self.run_action()
        self.wa.write.assert_not_called()
        self.bridge.run.assert_not_called()

    def test_dry_run_never_transmits_or_writes(self):
        self.env.context = {'mebel_vision_dry_run': True}
        self.wa.mail_message_id.attachment_ids = [self.photo]
        self.run_action()
        self.wa.write.assert_not_called()
        self.bridge.run.assert_not_called()

    def test_existing_catalog_reply_still_prevents_ai_reply(self):
        self.design.run.side_effect = lambda: setattr(self, 'replied', True)
        self.run_action()
        self.bridge.run.assert_not_called()
        self.wa.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
