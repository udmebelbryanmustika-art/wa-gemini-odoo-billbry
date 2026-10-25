from pathlib import Path
import unittest
from unittest.mock import MagicMock

CODE = compile(Path(__file__).with_name('odoo_inbound_action.py').read_text(),
               'odoo_inbound_action.py', 'exec')


class InboundRoutingTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.wa_account_id.id = 9
        self.wa.message_type = 'inbound'
        self.wa.msg_uid = 'test-only'
        self.wa.mail_message_id = True
        self.records = MagicMock()
        self.records.with_user.return_value.with_context.return_value = [self.wa]
        self.messages = MagicMock()
        self.messages.with_user.return_value.with_context.return_value = self.messages
        self.actions = MagicMock()
        self.actions.with_user.return_value = self.actions
        self.env = {'whatsapp.message': self.messages, 'ir.actions.server': self.actions}

    def run_action(self):
        exec(CODE, {'env': self.env, 'records': self.records})

    def test_image_reply_prevents_a_second_ai_reply(self):
        self.messages.search.side_effect = [False, True]
        self.run_action()
        self.assertEqual([c.args[0] for c in self.actions.browse.call_args_list], [1795])

    def test_other_requests_keep_the_existing_ai_connector(self):
        self.messages.search.side_effect = [False, False]
        self.run_action()
        self.assertEqual([c.args[0] for c in self.actions.browse.call_args_list], [1795, 1780])

    def test_already_replied_message_is_not_replayed(self):
        self.messages.search.return_value = True
        self.run_action()
        self.actions.browse.assert_not_called()

    def test_other_company_account_does_not_call_any_action(self):
        self.wa.wa_account_id.id = 3
        self.run_action()
        self.actions.browse.assert_not_called()


if __name__ == '__main__':
    unittest.main()
