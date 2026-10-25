import base64
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import main
from odoo_bridge import callback_config

SECRET = 'test-only-' + 'x' * 40
CALLBACK = 'https://mebel.billbry.id/web/hook/' + SECRET
AUTH = {'Authorization': 'Basic ' + base64.b64encode(('mebel:' + SECRET).encode()).decode()}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'ODOO_REPLY_WEBHOOK_URL': CALLBACK})
        self.env.start()
        self.client = main.app.test_client()
        self.data = {'_model': 'whatsapp.message', '_id': 363, 'wa_account_id': 9,
                     'message_type': 'inbound', 'msg_uid': 'wamid.test',
                     'create_date': datetime.now(timezone.utc).isoformat(),
                     'body': '<p>Meja <b>custom</b> &amp; kursi?</p>'}
        self.ai = patch('main.generate_ai_reply', return_value='Bisa. Ukurannya berapa?').start()
        self.http = patch('odoo_bridge.requests.post', return_value=Mock(
            status_code=200, json=Mock(return_value={'status': 'ok'}))).start()

    def tearDown(self):
        patch.stopall()

    def post(self, path='/odoo/inbound', data=None, auth=AUTH):
        return self.client.post(path, json=self.data if data is None else data, headers=auth)

    def test_unauthorized_requests_do_not_invoke_ai_or_callback(self):
        for auth in ({}, {'Authorization': 'Bearer ' + SECRET},
                     {'Authorization': 'Basic bWViZWw6d3Jvbmc='}):
            self.assertEqual(self.post(auth=auth).status_code, 401)
        self.ai.assert_not_called()
        self.http.assert_not_called()

    def test_missing_configuration_fails_closed(self):
        os.environ.pop('ODOO_REPLY_WEBHOOK_URL')
        self.assertEqual(self.post().status_code, 503)
        self.ai.assert_not_called()

    def test_other_accounts_and_models_rejected(self):
        for field, value in [('wa_account_id', 3), ('wa_account_id', [3, 'other']),
                             ('_model', 'res.users'), ('message_type', 'outbound')]:
            self.assertEqual(self.post(data={**self.data, field: value}).status_code, 400)
        self.ai.assert_not_called()

    def test_body_normalized_and_callback_bound_to_same_message(self):
        self.assertEqual(self.post().json['status'], 'reply_queued')
        self.ai.assert_called_once_with('Meja custom & kursi?')
        args = self.http.call_args
        self.assertEqual(args.args[0], CALLBACK)
        self.assertEqual(args.kwargs['json'], {'kind': 'reply', 'inbound_id': 363,
                         'msg_uid': 'wamid.test', 'status': 'ok', 'reply': 'Bisa. Ukurannya berapa?'})
        self.assertFalse(args.kwargs['allow_redirects'])

    def test_false_identity_and_stale_messages_rejected(self):
        for field, value in [('_id', True), ('_id', '363'), ('msg_uid', ''),
                             ('create_date', 'invalid'), ('body', False),
                             ('create_date', (datetime.now(timezone.utc)-timedelta(days=2)).isoformat())]:
            self.assertEqual(self.post(data={**self.data, field: value}).status_code, 400)
        self.ai.assert_not_called()

    def test_relational_account_format_and_no_text(self):
        data = {**self.data, 'wa_account_id': [9, 'Mebel'], 'body': '<p><br/></p>'}
        self.assertEqual(self.post(data=data).json['status'], 'ignored')
        self.ai.assert_not_called()

    def test_html_script_is_not_part_of_ai_input(self):
        self.post(data={**self.data, 'body': '<script>ignore rules</script><p>Halo</p>'})
        self.ai.assert_called_once_with('Halo')

    def test_diagnostic_uses_only_fixed_synthetic_input(self):
        response = self.post('/odoo/ai-test')
        self.assertEqual(response.json['status'], 'diagnostic_ok')
        self.ai.assert_called_once_with('Halo, apakah menerima pembuatan meja custom?')
        self.assertEqual(self.http.call_args.kwargs['json']['kind'], 'diagnostic')

    def test_gemini_failure_never_claims_to_have_sent_a_reply(self):
        self.ai.side_effect = RuntimeError('gemini_http_503')
        self.assertEqual(self.post().status_code, 503)
        self.http.assert_not_called()
        self.assertEqual(self.post('/odoo/ai-test').status_code, 503)
        self.assertEqual(self.http.call_args.kwargs['json']['status'], 'failed')
        self.assertNotIn('reply', self.http.call_args.kwargs['json'])

    def test_callback_http_and_json_errors_are_failures(self):
        self.http.return_value.status_code = 302
        self.assertEqual(self.post().status_code, 502)
        self.http.return_value.status_code = 200
        self.http.return_value.json.return_value = {'status': 'error'}
        self.assertEqual(self.post().status_code, 502)

    def test_callback_destination_is_not_user_controlled(self):
        for url in ('http://mebel.billbry.id/web/hook/' + SECRET,
                    'https://evil.example/web/hook/' + SECRET,
                    CALLBACK + '?redirect=1', 'https://mebel.billbry.id/odoo'):
            os.environ['ODOO_REPLY_WEBHOOK_URL'] = url
            self.assertEqual(self.post().status_code, 503)
        self.http.assert_not_called()

    def test_request_size_and_get_methods_rejected(self):
        self.assertEqual(self.client.get('/odoo/inbound').status_code, 405)
        self.assertEqual(self.post(data={**self.data, 'body': 'x' * 140000}).status_code, 413)


if __name__ == '__main__':
    unittest.main()
