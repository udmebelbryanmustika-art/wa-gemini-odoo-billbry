"""Bounded Gemini recovery; upstream bodies and credentials never enter logs."""
import logging
import re
import time

import requests

log = logging.getLogger(__name__)
TRANSIENT = {408, 429, 500, 502, 503, 504}


def model_id(value):
    value = value.strip().removeprefix('models/')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', value):
        raise RuntimeError('gemini_model_invalid')
    return value


def generate_reply(text, *, api_key, model, instruction, fallback_model=''):
    if not api_key or not api_key.strip():
        raise RuntimeError('gemini_key_missing')
    primary = model_id(model)
    fallback = model_id(fallback_model) if fallback_model.strip() else primary
    # The old Flash-Lite fallback returned 404 in this deployment. Reuse the
    # working primary instead of spending another attempt on that endpoint.
    if fallback == 'gemini-2.5-flash-lite':
        fallback = primary
    # At most two requests: primary, then configured fallback.
    # No automatic retry on invalid key, permission, missing model, or blocked output.
    models = [primary, fallback]
    last_error = 'gemini_unavailable'
    for attempt, selected in enumerate(models):
        if attempt:
            time.sleep(0.25)
        generation = {'maxOutputTokens': 512, 'temperature': 0.4}
        if selected.startswith('gemini-3.1-flash-lite'):
            generation['thinkingConfig'] = {'thinkingLevel': 'minimal'}
        try:
            response = requests.post(
                'https://generativelanguage.googleapis.com/v1beta/models/'
                + selected + ':generateContent',
                headers={'x-goog-api-key': api_key.strip(), 'Content-Type': 'application/json'},
                json={'systemInstruction': {'parts': [{'text': instruction}]},
                      'contents': [{'role': 'user', 'parts': [{'text': text[:12000]}]}],
                      'generationConfig': generation},
                timeout=(3, 6))
        except (requests.Timeout, requests.ConnectionError):
            last_error = 'gemini_transport_error'
            log.warning('gemini_attempt_failed attempt=%s reason=transport', attempt + 1)
            continue
        except requests.RequestException:
            raise RuntimeError('gemini_transport_error') from None
        if not response.ok:
            status = response.status_code
            log.warning('gemini_attempt_failed attempt=%s http_status=%s', attempt + 1, status)
            last_error = 'gemini_http_' + str(status)
            if status in TRANSIENT:
                continue
            raise RuntimeError(last_error)
        try:
            data = response.json()
            candidates = data.get('candidates', [])
            candidate = candidates[0] if candidates else {}
            if data.get('promptFeedback', {}).get('blockReason') or candidate.get('finishReason') in {
                    'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII'}:
                raise RuntimeError('gemini_output_blocked')
            parts = candidate.get('content', {}).get('parts', [])
            reply = ''.join(part.get('text', '') for part in parts
                            if isinstance(part, dict) and not part.get('thought')).strip()
        except (ValueError, TypeError, AttributeError, IndexError):
            raise RuntimeError('gemini_invalid_response') from None
        if not reply:
            raise RuntimeError('gemini_empty_reply')
        log.info('gemini_generation_succeeded attempt=%s', attempt + 1)
        return reply[:4000]
    raise RuntimeError(last_error)

