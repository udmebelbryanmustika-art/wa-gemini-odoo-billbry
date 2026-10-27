"""Offline ZapClaw event adapter. Not registered as a production HTTP route.

Authentication and account scoping happen before customer content is returned.
The eventual consumer must persist/deduplicate events and apply handoff state
atomically before enabling delivery. This module never sends or fetches anything.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re


MEBEL_NUMBER = '6285187219372'


class CoexistenceError(ValueError):
    pass


@dataclass(frozen=True)
class ConversationEvent:
    event: str
    phone_id: str
    message_id: str
    customer_id: str
    occurred_at: datetime
    message_type: str
    text: str

    @property
    def deduplication_key(self):
        # A delivery retry or manual replay must not create another chat entry.
        return (self.phone_id, self.event, self.message_id)

    @property
    def requires_handoff(self):
        return self.event == 'message.echo'


def parse_event(raw_body, signature, *, secret, phone_id):
    """Verify and normalize received/phone-sent messages for the Mebel number.

    phone_id must come from the verified connection after onboarding, not from
    the incoming payload. Do not assume it stays unchanged during migration.
    Other event types are explicitly unsupported (never acknowledged here).
    """
    if (not isinstance(secret, str) or len(secret) < 16
            or not isinstance(phone_id, str) or not re.fullmatch(r'[0-9]{5,32}', phone_id)):
        raise CoexistenceError('configuration_required')
    if not isinstance(raw_body, bytes) or len(raw_body) > 3 * 1024 * 1024:
        raise CoexistenceError('invalid_body')
    expected = 'sha256=' + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    if (not isinstance(signature, str)
            or not hmac.compare_digest(expected.encode(), signature.encode())):
        raise CoexistenceError('invalid_signature')
    try:
        payload = json.loads(raw_body)
    except (ValueError, UnicodeDecodeError):
        raise CoexistenceError('invalid_json') from None
    if not isinstance(payload, dict):
        raise CoexistenceError('invalid_payload')
    account = payload.get('account')
    if not isinstance(account, dict) or account.get('phone_number_id') != phone_id:
        raise CoexistenceError('wrong_account')
    display = account.get('display_phone_number')
    if (not isinstance(display, str)
            or re.sub(r'[+\s().-]', '', display) != MEBEL_NUMBER):
        raise CoexistenceError('wrong_number')
    event = payload.get('event')
    if event not in {'message.received', 'message.echo'}:
        raise CoexistenceError('unsupported_event')
    data = payload.get('data')
    if not isinstance(data, dict):
        raise CoexistenceError('invalid_message')
    uid = data.get('message_id')
    if not isinstance(uid, str) or not uid.startswith('wamid.') or len(uid) > 512:
        raise CoexistenceError('invalid_message_id')
    # Preserve username-only customer identities; never replace one with a
    # guessed phone number. Direction determines which side is the customer.
    customer = data.get('user_id') or data.get('to' if event == 'message.echo' else 'from')
    if (not isinstance(customer, str)
            or not re.fullmatch(r'(?:[A-Z]{2}\.[A-Za-z0-9]{1,160}|[1-9][0-9]{7,14})', customer)
            or customer == MEBEL_NUMBER):
        raise CoexistenceError('invalid_customer')
    timestamp = data.get('timestamp')
    if not isinstance(timestamp, str) or not re.fullmatch(r'[0-9]{1,12}', timestamp):
        raise CoexistenceError('invalid_timestamp')
    try:
        occurred_at = datetime.fromtimestamp(int(timestamp), timezone.utc)
    except (OverflowError, OSError, ValueError):
        raise CoexistenceError('invalid_timestamp') from None
    message_type = data.get('type')
    if not isinstance(message_type, str) or not re.fullmatch(r'[a-z_]{1,40}', message_type):
        raise CoexistenceError('invalid_message_type')
    text = ''
    if message_type == 'text':
        content = data.get('text')
        text = content.get('body') if isinstance(content, dict) else None
        if not isinstance(text, str) or not text.strip() or len(text) > 24000:
            raise CoexistenceError('invalid_text')
    # A photo/audio/document from a human must pause the bot too. Actual media
    # retrieval and attachment handling are deliberately not implemented yet.
    return ConversationEvent(event, phone_id, uid, customer, occurred_at,
                             message_type, text)
