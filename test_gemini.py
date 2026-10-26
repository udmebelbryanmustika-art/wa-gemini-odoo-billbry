from unittest.mock import Mock
import pytest
import requests
import gemini_client as g
import main

@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(g.time, 'sleep', Mock())

def success(text='Bisa, silakan konfirmasi spesifikasi kepada admin.'):
    r = Mock(ok=True, status_code=200)
    r.json.return_value = {'candidates': [{'content': {'parts': [{'text': text}]}}]}
    return r

def run():
    return g.generate_reply('Meja custom?', api_key='private-key', model='gemini-3.1-flash-lite',
                            instruction='Mebel', fallback_model='gemini-2.5-flash-lite')

def test_503_recovers_on_same_model(monkeypatch):
    call = Mock(side_effect=[Mock(ok=False, status_code=503), success()])
    monkeypatch.setattr(g.requests, 'post', call)
    assert run().startswith('Bisa')
    assert call.call_count == 2
    assert call.call_args_list[0].args[0] == call.call_args_list[1].args[0]

def test_two_transient_failures_stop_without_broken_fallback(monkeypatch):
    call = Mock(side_effect=[Mock(ok=False, status_code=503), requests.Timeout('private'), success()])
    monkeypatch.setattr(g.requests, 'post', call)
    with pytest.raises(RuntimeError, match='gemini_transport_error'):
        run()
    assert call.call_count == 2
    assert 'gemini-2.5-flash-lite:generateContent' not in call.call_args.args[0]

@pytest.mark.parametrize('status', [400, 401, 403, 404])
def test_permanent_errors_not_retried(monkeypatch, status):
    call = Mock(return_value=Mock(ok=False, status_code=status))
    monkeypatch.setattr(g.requests, 'post', call)
    with pytest.raises(RuntimeError, match='gemini_http_' + str(status)):
        run()
    assert call.call_count == 1

def test_exhausted_retries_safe_logs(monkeypatch, caplog):
    call = Mock(side_effect=requests.Timeout('private-key customer-message'))
    monkeypatch.setattr(g.requests, 'post', call)
    with pytest.raises(RuntimeError, match='gemini_transport_error'):
        run()
    assert call.call_count == 2
    assert 'private-key' not in caplog.text and 'customer-message' not in caplog.text

def test_blocked_output_never_falls_back(monkeypatch):
    r = success()
    r.json.return_value = {'candidates': [{'finishReason': 'SAFETY'}]}
    call = Mock(return_value=r)
    monkeypatch.setattr(g.requests, 'post', call)
    with pytest.raises(RuntimeError, match='gemini_output_blocked'):
        run()
    assert call.call_count == 1

def test_thought_parts_are_not_sent(monkeypatch):
    r = success()
    r.json.return_value = {'candidates': [{'content': {'parts': [
        {'thought': True, 'text': 'internal'}, {'text': 'Jawaban'}]}}]}
    monkeypatch.setattr(g.requests, 'post', Mock(return_value=r))
    assert run() == 'Jawaban'

def test_probe_requires_token_and_never_sends_whatsapp(monkeypatch):
    monkeypatch.setenv('DIAGNOSTIC_TOKEN', 'diagnostic-only')
    ai = Mock(return_value='Balasan uji')
    send = Mock()
    monkeypatch.setattr(main, 'generate_ai_reply', ai)
    monkeypatch.setattr(main.requests, 'post', send)
    client = main.app.test_client()
    assert client.post('/admin/gemini-test').status_code == 401
    ai.assert_not_called()
    r = client.post('/admin/gemini-test', headers={'Authorization': 'Bearer diagnostic-only'},
                    json={'text': 'must not be used'})
    assert r.status_code == 200
    assert ai.call_args.args == ('Halo, apakah menerima pembuatan meja custom?',)
    send.assert_not_called()

def test_probe_failure_is_not_success(monkeypatch):
    monkeypatch.setenv('DIAGNOSTIC_TOKEN', 'diagnostic-only')
    monkeypatch.setattr(main, 'generate_ai_reply', Mock(side_effect=RuntimeError('gemini_http_503')))
    r = main.app.test_client().post('/admin/gemini-test',
            headers={'Authorization': 'Bearer diagnostic-only'})
    assert r.status_code == 502 and r.json['status'] == 'failed'
