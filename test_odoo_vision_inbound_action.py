import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

CODE = compile(Path(__file__).with_name('odoo_vision_inbound_action.py').read_text(),
               'odoo_vision_inbound_action.py', 'exec')


class Environment(dict):
    context = {}


class VisionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
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
        self.photo = SimpleNamespace(mimetype='image/png', raw=SimpleNamespace(
            size=123, to_base64=MagicMock(return_value='test-only-image')))

    def run_action(self):
        exec(CODE, {'env': self.env, 'records': self.records, 'datetime': datetime,
                    'log': MagicMock()})

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
        self.assertEqual(self.wa.write.call_args.args[0]['x_mebel_ai_context'],
                         'Citra: Meja dengan laci\nPelanggan: 120 x 60 cm')
        history_domain = self.messages.search.call_args.args[0]
        self.assertIn(('wa_account_id', '=', 9), history_domain)
        self.assertIn(('mail_message_id.res_id', '=', 20), history_domain)

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
