import hashlib
import hmac
import json
import os
import time
import unittest
from unittest.mock import Mock, patch

import fakeredis
from flask import Flask
from zapclaw_bridge import (Store, zapclaw, process_job, PHONE, NUMBER_ID)


class RedisStore(Store):
    def __init__(self):
        self.redis = fakeredis.FakeRedis(decode_responses=True)

    def command(self, *args):
        return self.redis.execute_command(*args)


class CoexistenceTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'ZAPCLAW_ENABLED': 'true', 'ZAPCLAW_WEBHOOK_SECRET': 'test-only'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.store = RedisStore()
        app = Flask(__name__)
        app.register_blueprint(zapclaw)
        self.client = app.test_client()
        self.job = {'chat': 'zc:chat:test', 'to': '6281230000000', 'text': 'Meja custom?',
                    'message_id': 'wamid.test1', 'timestamp': int(time.time())}

    def test_new_session_excludes_old_and_undated_history(self):
        history_key = self.job['chat'] + ':history'
        self.store.command('RPUSH', history_key,
                           json.dumps({'customer': 'undated discussion'}),
                           json.dumps({'customer': 'old discussion',
                                       'timestamp': self.job['timestamp'] - 86400}))
        generate = Mock(return_value='Halo, saya Citra.')
        process_job(self.job, self.store, generate, Mock(return_value=201))
        prompt = generate.call_args.args[0]
        self.assertIn('Tahap percakapan: PEMBUKA', prompt)
        self.assertNotIn('discussion', prompt)
        self.assertEqual(self.store.redis.llen(history_key), 3)

    def test_active_session_keeps_current_context(self):
        self.store.command('RPUSH', self.job['chat'] + ':history',
                           json.dumps({'customer': 'current dimensions',
                                       'timestamp': self.job['timestamp'] - 60}))
        generate = Mock(return_value='Baik, saya lanjutkan.')
        process_job(self.job, self.store, generate, Mock(return_value=201))
        prompt = generate.call_args.args[0]
        self.assertIn('Tahap percakapan: LANJUTAN', prompt)
        self.assertIn('current dimensions', prompt)

    def test_explicit_reset_keeps_old_turns_out_of_next_reply(self):
        self.store.command('RPUSH', self.job['chat'] + ':history',
                           json.dumps({'customer': 'previous order',
                                       'timestamp': self.job['timestamp'] - 60}))
        generate = Mock(return_value='Halo, saya Citra.')
        send = Mock(return_value=201)
        process_job(dict(self.job, text='Mulai konsultasi baru'), self.store, generate, send)
        process_job(dict(self.job, message_id='next', text='Butuh lemari'), self.store, generate, send)
        prompt = generate.call_args.args[0]
        self.assertIn('Tahap percakapan: LANJUTAN', prompt)
        self.assertNotIn('previous order', prompt)

    def payload(self, event='message.received'):
        return {'event': event, 'account': {'phone_number_id': NUMBER_ID, 'display_phone_number': PHONE},
                'data': {'from': self.job['to'], 'to': self.job['to'], 'message_id': self.job['message_id'],
                         'timestamp': str(self.job['timestamp']), 'type': 'text', 'text': {'body': 'Halo'}}}

    def post(self, payload):
        raw = json.dumps(payload).encode()
        sig = 'sha256=' + hmac.new(b'test-only', raw, hashlib.sha256).hexdigest()
        return self.client.post('/webhooks/zapclaw', data=raw, content_type='application/json',
                                headers={'X-ZapClaw-Signature': sig})

    def test_forged_request_has_no_side_effect(self):
        with patch('zapclaw_bridge.enqueue') as queue:
            self.assertEqual(self.client.post('/webhooks/zapclaw', json=self.payload()).status_code, 401)
            queue.assert_not_called()

    def test_wrong_number_and_old_history_do_not_queue(self):
        with patch('zapclaw_bridge.enqueue') as queue:
            p = self.payload(); p['account']['phone_number_id'] = 'other'
            self.assertEqual(self.post(p).status_code, 200)
            p = self.payload(); p['data']['timestamp'] = str(int(time.time()) - 3600)
            self.assertEqual(self.post(p).status_code, 200)
            queue.assert_not_called()

    def test_queue_failure_is_not_acknowledged(self):
        with patch('zapclaw_bridge.Store', return_value=self.store), patch('zapclaw_bridge.enqueue', side_effect=RuntimeError()):
            self.assertEqual(self.post(self.payload()).status_code, 503)

    def test_successful_ingress_durable_queue(self):
        with patch('zapclaw_bridge.Store', return_value=self.store), patch('zapclaw_bridge.enqueue') as queue:
            self.assertEqual(self.post(self.payload()).json['status'], 'queued')
            self.assertEqual(queue.call_args.args[0]['text'], 'Halo')

    def test_echo_pauses_and_does_not_queue_or_reply(self):
        with patch('zapclaw_bridge.Store', return_value=self.store), patch('zapclaw_bridge.enqueue') as queue:
            self.assertEqual(self.post(self.payload('message.echo')).json['status'], 'admin_handoff')
            queue.assert_not_called()
            self.assertTrue(list(self.store.redis.scan_iter('*:handoff')))

    def test_customer_admin_request_pauses_without_ai(self):
        p = self.payload(); p['data']['text']['body'] = 'Hubungi Admin'
        with patch('zapclaw_bridge.Store', return_value=self.store), patch('zapclaw_bridge.enqueue') as queue:
            self.assertEqual(self.post(p).json['status'], 'admin_handoff')
            queue.assert_not_called()

    def test_duplicate_deliveries_send_exactly_once(self):
        generate, send = Mock(return_value='Bisa, Kak. Berapa ukurannya?'), Mock(return_value=201)
        process_job(self.job, self.store, generate, send)
        process_job(self.job, self.store, generate, send)
        send.assert_called_once()
        self.assertEqual(self.store.redis.llen(self.job['chat'] + ':history'), 1)

    def test_phone_reply_while_generating_prevents_ai_send(self):
        def generate(_):
            self.store.command('SET', self.job['chat'] + ':handoff', 'phone_admin', 'EX', 86400)
            return 'AI reply'
        send = Mock(return_value=201)
        process_job(self.job, self.store, generate, send)
        send.assert_not_called()

    def test_unknown_send_is_never_retried(self):
        send = Mock(side_effect=TimeoutError())
        for _ in range(2):
            process_job(self.job, self.store, Mock(return_value='Reply'), send)
        send.assert_called_once()
        self.assertEqual(self.store.command('GET', self.job['chat'] + ':handoff'), 'send_unknown')

    def test_definite_refusal_pauses_for_admin(self):
        send = Mock(return_value=403)
        process_job(self.job, self.store, Mock(return_value='Reply'), send)
        self.assertEqual(self.store.command('GET', self.job['chat'] + ':handoff'), 'send_failed')

    def test_redis_down_never_sends(self):
        send = Mock()
        with self.assertRaises(RuntimeError):
            process_job(self.job, Mock(script=Mock(side_effect=RuntimeError('down'))), Mock(), send)
        send.assert_not_called()

    def test_generation_failure_retries_without_send_marker(self):
        with self.assertRaises(RuntimeError):
            process_job(self.job, self.store, Mock(side_effect=RuntimeError('gemini')), Mock())
        send = Mock(return_value=201)
        process_job(self.job, self.store, Mock(return_value='Recovered'), send)
        send.assert_called_once()

    def test_no_key_or_url_cannot_call_redis(self):
        with patch.dict(os.environ, {'KV_REST_API_URL': '', 'KV_REST_API_TOKEN': ''}), patch('zapclaw_bridge.requests.post') as post:
            with self.assertRaises(RuntimeError): Store().command('GET', 'test')
            post.assert_not_called()


if __name__ == '__main__':
    unittest.main()
