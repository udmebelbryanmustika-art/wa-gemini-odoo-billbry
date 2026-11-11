import copy
import hashlib
import hmac
import json

import pytest

from coexistence_events import CoexistenceError, parse_event


SECRET = 'synthetic-signing-secret-for-tests'
PHONE_ID = '123456789012345'
PAYLOAD = {
    'event': 'message.received',
    'account': {'phone_number_id': PHONE_ID,
                'display_phone_number': '+62 851-8721-9372'},
    'data': {'from': '6281234567890', 'message_id': 'wamid.synthetic',
             'type': 'text', 'timestamp': '1793060000',
             'text': {'body': 'Meja custom 120 cm'}},
}


def parse(payload, **kwargs):
    raw = json.dumps(payload).encode()
    signature = 'sha256=' + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return parse_event(raw, signature, secret=SECRET, phone_id=PHONE_ID, **kwargs)


def test_customer_and_admin_have_opposite_directions():
    inbound = parse(PAYLOAD)
    echo = copy.deepcopy(PAYLOAD)
    echo['event'] = 'message.echo'
    echo['data']['to'] = echo['data'].pop('from')
    outbound = parse(echo)
    assert inbound.customer_id == outbound.customer_id
    assert not inbound.requires_handoff
    assert outbound.requires_handoff
    assert inbound.deduplication_key != outbound.deduplication_key
    assert outbound.deduplication_key == parse(echo).deduplication_key


def test_media_echo_requests_handoff_without_fetching_media():
    payload = copy.deepcopy(PAYLOAD)
    payload['event'] = 'message.echo'
    payload['data'].update(to='6281234567890', type='image',
                           image={'media_url': 'http://127.0.0.1/private'})
    payload['data'].pop('text')
    event = parse(payload)
    assert event.requires_handoff
    assert event.text == ''


def test_username_only_customer_is_preserved():
    payload = copy.deepcopy(PAYLOAD)
    payload['data'].update(user_id='ID.ABC123', **{'from': None})
    assert parse(payload).customer_id == 'ID.ABC123'


@pytest.mark.parametrize('signature', [None, '', 'sha256=bad', '💥'])
def test_untrusted_signature_rejected(signature):
    with pytest.raises(CoexistenceError, match='invalid_signature'):
        parse_event(b'{}', signature, secret=SECRET, phone_id=PHONE_ID)


@pytest.mark.parametrize('area,field,value,error', [
    ('account', 'phone_number_id', '99999999', 'wrong_account'),
    ('account', 'display_phone_number', '+628111111111', 'wrong_number'),
    ('data', 'message_id', '', 'invalid_message_id'),
    ('data', 'from', 'https://attacker.test', 'invalid_customer'),
    ('data', 'timestamp', '2026-10-27T00:00:00Z', 'invalid_timestamp'),
    ('data', 'text', {'body': None}, 'invalid_text'),
])
def test_malformed_or_cross_company_events_rejected(area, field, value, error):
    payload = copy.deepcopy(PAYLOAD)
    payload[area][field] = value
    with pytest.raises(CoexistenceError, match=error):
        parse(payload)


def test_status_event_is_never_treated_as_customer_message():
    payload = copy.deepcopy(PAYLOAD)
    payload['event'] = 'message.status'
    with pytest.raises(CoexistenceError, match='unsupported_event'):
        parse(payload)


def test_missing_configuration_fails_closed():
    with pytest.raises(CoexistenceError, match='configuration_required'):
        parse_event(b'{}', '', secret='', phone_id=PHONE_ID)
