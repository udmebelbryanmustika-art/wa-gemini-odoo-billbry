import datetime
from pathlib import Path
import unittest
from unittest.mock import MagicMock


class UserError(Exception):
    pass


CODE = compile(Path(__file__).with_name('odoo_reply_action.py').read_text(),
               'odoo_reply_action.py', 'exec')


class OdooReplyGuards(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.__len__.return_value = 1
        self.wa.with_user.return_value = self.wa
        self.wa.try_lock_for_update.return_value = self.wa
        self.wa.wa_account_id.id = 9
        self.wa.message_type = 'inbound'
        self.wa.msg_uid = 'wamid.test'
        self.wa.id = 363
        self.wa.create_date = datetime.datetime.utcnow()
        self.wa.mail_message_id.model = 'discuss.channel'
        self.wa.mail_message_id.res_id = 20
        self.messages = MagicMock()
        self.messages.with_user.return_value = self.messages
        self.outgoing = MagicMock()
        self.outgoing.id = 999
        self.messages.search.side_effect = [False, self.outgoing]
        self.channels = MagicMock()
        self.channels.with_user.return_value = self.channels
        self.channel = self.channels.browse.return_value.exists.return_value
        self.env = {'whatsapp.message': self.messages, 'discuss.channel': self.channels}
        self.logs = MagicMock()
        self.payload = {'kind': 'reply', 'inbound_id': 363, 'msg_uid': 'wamid.test', 'reply': 'Bisa. Ukurannya berapa?'}

    def run_action(self):
        exec(CODE, {'env': self.env, 'records': self.wa, 'payload': self.payload,
                    'datetime': datetime, 'UserError': UserError, 'log': self.logs})

    def test_valid_reply_uses_original_channel_and_links_parent(self):
        self.run_action()
        self.channels.browse.assert_called_once_with(20)
        self.channel.message_post.assert_called_once_with(
            body='Bisa. Ukurannya berapa?', message_type='whatsapp_message', subtype_xmlid='mail.mt_comment')
        self.outgoing.write.assert_called_once_with({'parent_id': 363})

    def test_wrong_account_never_reaches_channel(self):
        self.wa.wa_account_id.id = 3
        with self.assertRaisesRegex(UserError, 'invalid_mebel_inbound'):
            self.run_action()
        self.channels.browse.assert_not_called()

    def test_mismatched_message_uid_rejected(self):
        self.payload['msg_uid'] = 'another-message'
        with self.assertRaisesRegex(UserError, 'mebel_message_mismatch'):
            self.run_action()
        self.channel.message_post.assert_not_called()

    def test_expired_and_busy_messages_do_not_send(self):
        self.wa.create_date -= datetime.timedelta(days=2)
        with self.assertRaisesRegex(UserError, 'expired'):
            self.run_action()
        self.wa.create_date = datetime.datetime.utcnow()
        self.wa.try_lock_for_update.return_value = False
        with self.assertRaisesRegex(UserError, 'busy'):
            self.run_action()
        self.channel.message_post.assert_not_called()

    def test_existing_reply_does_not_send_again(self):
        self.messages.search.side_effect = [self.outgoing]
        self.run_action()
        self.channel.message_post.assert_not_called()

    def test_diagnostic_logs_proof_but_never_sends(self):
        self.payload.update(kind='diagnostic', status='ok')
        self.run_action()
        self.logs.assert_called_once()
        self.assertIn('MEBEL_GEMINI_TEST_OK', self.logs.call_args.args[0])
        self.channel.message_post.assert_not_called()
        self.wa.try_lock_for_update.assert_not_called()

    def test_unknown_operation_and_wrong_channel_rejected(self):
        self.payload['kind'] = 'delete'
        with self.assertRaisesRegex(UserError, 'invalid_mebel_operation'):
            self.run_action()
        self.payload['kind'] = 'reply'
        self.wa.mail_message_id.model = 'res.users'
        with self.assertRaisesRegex(UserError, 'invalid_mebel_channel'):
            self.run_action()
        self.channel.message_post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
