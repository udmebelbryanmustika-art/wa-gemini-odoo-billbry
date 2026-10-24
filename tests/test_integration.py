import hashlib
import hmac
import json
from unittest.mock import Mock

import pytest
import requests
import main


@pytest.fixture(autouse=True)
def config(monkeypatch):
    for key in ('META_ACCESS_TOKEN', 'META_PHONE_ID', 'META_APP_SECRET', 'VERIFY_TOKEN',
                'GEMINI_API_KEY', 'DIAGNOSTIC_TOKEN', 'ODOO_CRM_ENABLED', 'ODOO_COMPANY_ID',
                'ODOO_API_KEY', 'ODOO_URL', 'ODOO_DB'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('META_APP_SECRET', 'test-secret')
    monkeypatch.setenv('META_ACCESS_TOKEN', 'test-access')
    monkeypatch.setenv('META_PHONE_ID', '1361790767020113')


def payload(messages=None, phone='1361790767020113'):
    return {'object': 'whatsapp_business_account', 'entry': [{'changes': [{'value': {
        'metadata': {'phone_number_id': phone}, 'messages': messages if messages is not None else [
            {'id': 'wamid.inbound', 'from': '628111111111', 'type': 'text',
             'text': {'body': 'Meja custom?'}}]}}]}]}


def post(data):
    body = json.dumps(data).encode()
    signature = 'sha256=' + hmac.new(b'test-secret', body, hashlib.sha256).hexdigest()
    return main.app.test_client().post('/webhook', data=body, content_type='application/json',
                                      headers={'X-Hub-Signature-256': signature})


def test_health_never_claims_live_validation():
    result = main.app.test_client().get('/health').json
    assert result['live_api_validated'] is False
    assert 'VERIFY_TOKEN' in result['missing']
    assert 'test-access' not in str(result)


@pytest.mark.parametrize('path', ['/privacy', '/data-deletion'])
def test_privacy_and_deletion_pages_available_without_credentials(path):
    response = main.app.test_client().get(path)
    assert response.status_code == 200
    assert 'UD BILLBRY MEBEL' in response.text
    assert 'udmebelbryanmustika@gmail.com' in response.text
    assert 'test-access' not in response.text


def test_verification_has_no_default_secret(monkeypatch):
    client = main.app.test_client()
    query = {'hub.mode': 'subscribe', 'hub.verify_token': '', 'hub.challenge': '42'}
    assert client.get('/webhook', query_string=query).status_code == 403
    monkeypatch.setenv('VERIFY_TOKEN', 'test-verify')
    query['hub.verify_token'] = 'test-verify'
    response = client.get('/webhook', query_string=query)
    assert response.status_code == 200 and response.text == '42'


def test_forged_payload_never_calls_integrations(monkeypatch):
    handler = Mock()
    monkeypatch.setattr(main, 'ai_reply', handler)
    assert main.app.test_client().post('/webhook', json=payload()).status_code == 401
    handler.assert_not_called()


def test_missing_app_secret_fails_closed(monkeypatch):
    monkeypatch.delenv('META_APP_SECRET')
    assert post(payload()).status_code == 503


def test_wrong_phone_and_status_notifications_do_not_reply(monkeypatch):
    handler = Mock()
    monkeypatch.setattr(main, 'ai_reply', handler)
    assert post(payload(phone='other-company')).json['ignored'] == 1
    assert post(payload(messages=[])).status_code == 200
    handler.assert_not_called()


def test_batch_all_texts_are_processed_once_within_delivery(monkeypatch):
    message = payload()['entry'][0]['changes'][0]['value']['messages'][0]
    messages = [message, message, {**message, 'id': 'wamid.second'},
                {**message, 'id': 'wamid.image', 'type': 'image'}]
    monkeypatch.setattr(main, 'ai_reply', Mock(return_value='Silakan konsultasi admin.'))
    sender = Mock(return_value={'messages': [{'id': 'wamid.sent'}]})
    monkeypatch.setattr(main, 'meta_request', sender)
    result = post(payload(messages=messages))
    assert result.status_code == 200
    assert result.json == {'status': 'processed', 'processed': 2, 'ignored': 2, 'failed': 0}
    assert sender.call_count == 2


@pytest.mark.parametrize('error', ['meta_api_rejected', 'meta_transport_error'])
def test_failed_meta_delivery_is_not_success(monkeypatch, error):
    monkeypatch.setattr(main, 'ai_reply', Mock(return_value='Balasan'))
    monkeypatch.setattr(main, 'meta_request', Mock(side_effect=main.IntegrationError(error)))
    result = post(payload())
    assert result.status_code == 502
    assert result.json['failed'] == 1 and result.json['processed'] == 0


def test_missing_sent_message_id_is_failure(monkeypatch):
    monkeypatch.setattr(main, 'ai_reply', Mock(return_value='Balasan'))
    monkeypatch.setattr(main, 'meta_request', Mock(return_value={}))
    assert post(payload()).status_code == 502


def test_ai_failure_does_not_send_misleading_fallback(monkeypatch):
    monkeypatch.setattr(main, 'ai_reply', Mock(side_effect=main.IntegrationError('gemini_request_failed')))
    send = Mock()
    monkeypatch.setattr(main, 'meta_request', send)
    assert post(payload()).status_code == 502
    send.assert_not_called()


def test_meta_request_logs_only_safe_codes(monkeypatch, caplog):
    upstream = Mock(ok=False, status_code=401)
    upstream.json.return_value = {'error': {'code': 190, 'message': 'secret-token private text'}}
    call = Mock(return_value=upstream)
    monkeypatch.setattr(main.requests, 'request', call)
    with pytest.raises(main.IntegrationError, match='meta_api_rejected'):
        main.meta_request('GET', '1361790767020113')
    assert '190' in caplog.text and 'secret-token' not in caplog.text
    assert call.call_args.kwargs['timeout'] == (5, 25)


def test_transport_timeout_is_safe(monkeypatch):
    monkeypatch.setattr(main.requests, 'request', Mock(side_effect=requests.Timeout('private text')))
    with pytest.raises(main.IntegrationError, match='^meta_transport_error$'):
        main.meta_request('GET', '1361790767020113')


def test_diagnostics_require_separate_bearer_token(monkeypatch):
    call = Mock(return_value={'id': '1361790767020113', 'code_verification_status': 'VERIFIED'})
    monkeypatch.setattr(main, 'meta_request', call)
    client = main.app.test_client()
    assert client.get('/admin/meta-status').status_code == 401
    call.assert_not_called()
    monkeypatch.setenv('DIAGNOSTIC_TOKEN', 'test-diagnostic')
    response = client.get('/admin/meta-status', headers={'Authorization': 'Bearer test-diagnostic'})
    assert response.json['code_verification_status'] == 'VERIFIED'
    assert call.call_args.args[0] == 'GET'


def test_crm_disabled_by_default(monkeypatch):
    call = Mock()
    monkeypatch.setattr(main, 'odoo_call', call)
    assert main.save_crm_message('628111111111', 'Halo', 'wamid.test') == 'disabled'
    call.assert_not_called()


def test_crm_wrong_company_never_writes(monkeypatch):
    monkeypatch.setenv('ODOO_CRM_ENABLED', 'true')
    monkeypatch.setenv('ODOO_COMPANY_ID', '5')
    call = Mock(return_value=[{'name': 'UD Billbry Bor Sumur'}])
    monkeypatch.setattr(main, 'odoo_call', call)
    with pytest.raises(main.IntegrationError, match='odoo_company_mismatch'):
        main.save_crm_message('628111111111', 'Halo', 'wamid.test')
    assert call.call_count == 1


def test_crm_existing_message_is_not_created_again(monkeypatch):
    monkeypatch.setenv('ODOO_CRM_ENABLED', 'true')
    monkeypatch.setenv('ODOO_COMPANY_ID', '5')
    call = Mock(side_effect=[[{'name': 'UD BILLBRY MEBEL'}], [{'id': 99}]])
    monkeypatch.setattr(main, 'odoo_call', call)
    assert main.save_crm_message('628111111111', 'Halo', 'wamid.test') == 'existing'
    assert call.call_count == 2


def test_crm_create_scoped_and_html_escaped(monkeypatch):
    monkeypatch.setenv('ODOO_CRM_ENABLED', 'true')
    monkeypatch.setenv('ODOO_COMPANY_ID', '5')
    call = Mock(side_effect=[[{'name': 'UD BILLBRY MEBEL'}], [], [99]])
    monkeypatch.setattr(main, 'odoo_call', call)
    main.save_crm_message('628111111111', '<script>bad</script>', 'wamid.test')
    model, method, body = call.call_args.args
    assert (model, method) == ('crm.lead', 'create')
    assert body['vals_list'][0]['company_id'] == 5
    assert '<script>' not in body['vals_list'][0]['description']


def test_odoo_context_is_limited_to_mebel(monkeypatch):
    monkeypatch.setenv('ODOO_COMPANY_ID', '5')
    monkeypatch.setenv('ODOO_URL', 'https://example.odoo.com')
    monkeypatch.setenv('ODOO_API_KEY', 'test-odoo')
    response = Mock()
    response.json.return_value = []
    call = Mock(return_value=response)
    monkeypatch.setattr(main.requests, 'post', call)
    main.odoo_call('res.company', 'search_read', {'domain': []})
    assert call.call_args.kwargs['json']['context']['allowed_company_ids'] == [5]
