from datetime import datetime, timezone
import json
import os
import unittest
from unittest.mock import Mock, patch
import nara_followup as n
from test_zapclaw_bridge import RedisStore

class NaraTests(unittest.TestCase):
    def setUp(self):
        self.mode = patch.dict(os.environ, {'NARA_MODE':'preview'})
        self.mode.start(); self.addCleanup(self.mode.stop)
        self.now = int(datetime(2026,11,7,3,0,tzinfo=timezone.utc).timestamp()) # Saturday10WIB
        self.clock = patch('nara_followup.time.time',return_value=self.now)
        self.clock.start(); self.addCleanup(self.clock.stop)
        self.store = RedisStore(); self.chat = 'zc:chat:test-nara'
        self.job = {'chat':self.chat,'text':'meja custom','message_id':'in-1','timestamp':self.now}

    def consent(self):
        self.store.command('HSET',self.chat+':nara','notice_version',n.NOTICE_VERSION,'notice_at',self.now-60)
        n.observe(self.store,self.chat,'SETUJU FOLLOW UP','consent-1',self.now)

    def task(self):
        return {'chat':self.chat,'last_id':'consent-1','due':self.now+7200}

    def test_off_cannot_change_state_queue_or_generate(self):
        with patch.dict(os.environ,{'NARA_MODE':'off'}):
            store,generate,publish=Mock(),Mock(),Mock()
            n.observe(store,self.chat,'STOP','id',self.now)
            n.schedule(store,self.chat,publish=publish)
            self.assertEqual(n.prepare_draft(self.task(),store,generate,self.now+7200),'off')
            self.assertEqual(n.decorate_reply(store,self.job,'hello'),'hello')
            self.assertFalse(store.mock_calls); generate.assert_not_called(); publish.assert_not_called()

    def test_live_is_not_an_implemented_mode(self):
        with patch.dict(os.environ,{'NARA_MODE':'live'}):
            self.assertFalse(n.preview_enabled())

    def test_casual_yes_is_not_consent(self):
        n.observe(self.store,self.chat,'ya','id',self.now)
        self.assertNotIn('consent',n.state_for(self.store,self.chat))

    def test_consent_requires_a_delivered_current_notice(self):
        n.observe(self.store,self.chat,'SETUJU FOLLOW UP','id',self.now)
        self.assertNotIn('consent',n.state_for(self.store,self.chat))
        self.consent()
        state=n.state_for(self.store,self.chat)
        self.assertEqual(state['consent'],'allowed')
        self.assertEqual(state['consent_message_id'],'consent-1')
        self.assertEqual(state['consent_version'],n.NOTICE_VERSION)

    def test_duplicate_old_consent_cannot_undo_stop(self):
        self.consent()
        n.observe(self.store,self.chat,'STOP','stop',self.now+1)
        n.observe(self.store,self.chat,'SETUJU FOLLOW UP','consent-1',self.now)
        self.assertEqual(n.state_for(self.store,self.chat)['consent'],'revoked')

    def test_old_same_second_consent_cannot_undo_stop(self):
        self.consent()
        n.observe(self.store,self.chat,'STOP','stop',self.now)
        n.observe(self.store,self.chat,'SETUJU FOLLOW UP','other-old-consent',self.now)
        self.assertEqual(n.state_for(self.store,self.chat)['consent'],'revoked')

    def test_two_hour_delay_and_business_hours(self):
        self.consent(); publish=Mock()
        n.schedule(self.store,self.chat,publish=publish,now=self.now)
        self.assertEqual(publish.call_args.args[1],7200)
        sunday=int(datetime(2026,11,8,3,0,tzinfo=timezone.utc).timestamp())
        monday=n.business_due(sunday)
        self.assertEqual(datetime.fromtimestamp(monday,timezone.utc).isoformat(),'2026-11-09T01:00:00+00:00')

    def test_handoff_prevents_scheduling(self):
        self.consent(); self.store.command('SET',self.chat+':handoff','admin')
        publish=Mock();n.schedule(self.store,self.chat,publish=publish,now=self.now)
        publish.assert_not_called()

    def test_unconsented_conversation_has_no_schedule(self):
        publish=Mock(); n.schedule(self.store,self.chat,publish=publish,now=self.now)
        publish.assert_not_called()

    def test_new_customer_reply_cancels_old_task(self):
        self.consent(); n.observe(self.store,self.chat,'saya kirim ukuran','new',self.now+300)
        self.assertEqual(n.prepare_draft(self.task(),self.store,Mock(),self.now+7200),'cancelled')

    def test_phone_admin_cancels_task_and_removes_draft(self):
        self.consent(); self.store.command('SET',self.chat+':nara:draft','old')
        n.observe(self.store,self.chat,'','echo1',self.now+1,echo=True)
        self.assertFalse(self.store.command('EXISTS',self.chat+':nara:draft'))
        self.assertEqual(n.prepare_draft(self.task(),self.store,Mock(),self.now+7200),'cancelled')

    def test_expired_window_never_prepares(self):
        self.consent()
        self.assertEqual(n.prepare_draft(self.task(),self.store,Mock(),self.now+86401),'expired')

    def test_outside_business_hours_never_prepares(self):
        self.consent()
        self.assertEqual(n.prepare_draft(self.task(),self.store,Mock(),self.now+8*3600),'outside_hours')

    def test_prepare_saves_draft_once_without_sending_any_http(self):
        self.consent(); generate=Mock(return_value=n.TEMPLATE)
        with patch('requests.post',side_effect=AssertionError('No outbound HTTP permitted')):
            self.assertEqual(n.prepare_draft(self.task(),self.store,generate,self.now+7200),'draft_saved')
            self.assertEqual(n.prepare_draft(self.task(),self.store,generate,self.now+7200),'duplicate')
        generate.assert_called_once()
        draft=json.loads(self.store.command('GET',self.chat+':nara:draft'))
        self.assertEqual(draft['mode'],'draft_only')
        self.assertGreater(self.store.command('TTL',self.chat+':nara:draft'),0)

    def test_stop_during_ai_cancels_atomic_save(self):
        self.consent()
        def generate(_):
            n.observe(self.store,self.chat,'STOP','stop',self.now+10)
            return n.TEMPLATE
        self.assertEqual(n.prepare_draft(self.task(),self.store,generate,self.now+7200),'cancelled')
        self.assertFalse(self.store.command('EXISTS',self.chat+':nara:draft'))

    def test_already_ordered_and_payment_discussions_stop_preparation(self):
        for text in ['sudah order','sudah transfer','hubungi admin','komplain','tidak tertarik','jangan kirim lagi']:
            self.assertIn(n.classify(text),{'admin','optout'})

    def test_notice_is_not_repeated_after_successful_delivery(self):
        n.observe(self.store,self.chat,self.job['text'],self.job['message_id'],self.now)
        first=n.decorate_reply(self.store,self.job,'Bisa Kak')
        self.assertIn(n.NOTICE,first)
        with patch.object(n,'schedule'):
            n.note_success(self.store,self.job,first)
        self.assertEqual(n.decorate_reply(self.store,self.job,'Bisa Kak'),'Bisa Kak')

if __name__=='__main__': unittest.main()
