import unittest
from unittest.mock import Mock, patch

import requests

from gemini_client import generate_reply


def success():
    return Mock(ok=True, json=Mock(return_value={'candidates': [{
        'finishReason': 'STOP', 'content': {'parts': [{'text': 'Silakan kirim ukurannya.'}]}
    }]}))


class GeminiLatencyTests(unittest.TestCase):
    def generate(self, **overrides):
        options = dict(api_key='test-only', model='gemini-3.1-flash-lite',
                       instruction='Jawab singkat.', fallback_model='gemini-2.5-flash-lite')
        options.update(overrides)
        return generate_reply('Meja custom?', **options)

    @patch('gemini_client.requests.post')
    def test_image_is_forwarded_inline_with_caption(self, post):
        post.return_value = success()
        image = {'mime_type': 'image/png', 'data': 'test-only-validated-upstream'}
        self.generate(image=image)
        parts = post.call_args.kwargs['json']['contents'][0]['parts']
        self.assertEqual(parts, [{'text': 'Meja custom?'}, {'inlineData': {
            'mimeType': 'image/png', 'data': image['data']}}])

    @patch('gemini_client.requests.post')
    def test_normal_text_has_no_image_part(self, post):
        post.return_value = success()
        self.generate()
        self.assertEqual(post.call_args.kwargs['json']['contents'][0]['parts'],
                         [{'text': 'Meja custom?'}])

    @patch('gemini_client.time.sleep')
    @patch('gemini_client.requests.post')
    def test_timeout_recovers_without_the_broken_fallback(self, post, sleep):
        post.side_effect = [requests.Timeout(), success()]
        self.assertEqual(self.generate(), 'Silakan kirim ukurannya.')
        self.assertEqual(post.call_count, 2)
        for call in post.call_args_list:
            self.assertIn('/gemini-3.1-flash-lite:generateContent', call.args[0])
            self.assertEqual(call.kwargs['timeout'], (3, 6))
            self.assertEqual(call.kwargs['json']['generationConfig']['thinkingConfig'],
                             {'thinkingLevel': 'minimal'})
        sleep.assert_called_once_with(0.25)

    @patch('gemini_client.time.sleep')
    @patch('gemini_client.requests.post', side_effect=requests.Timeout())
    def test_retry_budget_is_bounded(self, post, sleep):
        with self.assertRaisesRegex(RuntimeError, 'gemini_transport_error'):
            self.generate()
        self.assertEqual(post.call_count, 2)

    @patch('gemini_client.requests.post', return_value=Mock(ok=False, status_code=403))
    def test_invalid_permission_does_not_retry(self, post):
        with self.assertRaisesRegex(RuntimeError, 'gemini_http_403'):
            self.generate()
        post.assert_called_once()

    @patch('gemini_client.time.sleep')
    @patch('gemini_client.requests.post')
    def test_explicit_alternative_model_is_preserved(self, post, sleep):
        post.side_effect = [Mock(ok=False, status_code=503), success()]
        self.generate(fallback_model='another-supported-model')
        self.assertIn('/another-supported-model:generateContent', post.call_args.args[0])
        self.assertNotIn('thinkingConfig', post.call_args.kwargs['json']['generationConfig'])


if __name__ == '__main__':
    unittest.main()
