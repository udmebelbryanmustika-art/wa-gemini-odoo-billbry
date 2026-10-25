import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock

CODE = compile(Path(__file__).with_name('odoo_design_action.py').read_text(),
               'odoo_design_action.py', 'exec')


class UserError(Exception):
    pass


class Environment(dict):
    context = {}


class DesignActionTests(unittest.TestCase):
    def setUp(self):
        self.wa = MagicMock()
        self.wa.id = 500
        self.wa.wa_account_id.id = 9
        self.wa.message_type = 'inbound'
        self.wa.msg_uid = 'test-only'
        self.wa.mail_message_id.model = 'discuss.channel'
        self.wa.mail_message_id.res_id = 20
        self.wa.create_date = datetime.datetime.utcnow()
        self.wa.body = '<p>Boleh minta gambar meja belajar?</p>'
        self.wa.x_mebel_design_options = False
        self.wa.x_mebel_crm_lead_id = False
        self.wa.try_lock_for_update.return_value = self.wa
        self.records = MagicMock()
        self.records.with_user.return_value.with_context.return_value = [self.wa]
        self.messages = MagicMock()
        self.messages.with_user.return_value = self.messages
        self.messages.with_context.return_value = self.messages
        self.history = []
        self.outgoing = MagicMock()
        self.messages.search.side_effect = lambda domain, **kw: (
            self.outgoing if any(x[0] == 'mail_message_id' for x in domain) else self.history)
        self.products = MagicMock()
        self.products.with_user.return_value.with_context.return_value = self.products
        self.catalog = {}
        for pid, name in [(683, 'Meja Belajar'), (682, 'Meja Kerja'), (684, 'Meja Laptop')]:
            self.catalog[pid] = SimpleNamespace(id=pid, name=name,
                company_id=SimpleNamespace(id=6), website_id=SimpleNamespace(id=7),
                website_published=True, image_1024=SimpleNamespace(size=123), website_url='/shop/model-' + str(pid))
        self.products.browse.side_effect = lambda pid: SimpleNamespace(exists=lambda: self.catalog.get(pid))
        self.attachments = MagicMock()
        self.attachments.with_user.return_value = self.attachments
        self.attachments.create.return_value = SimpleNamespace(id=70, mimetype='image/png')
        self.channels = MagicMock()
        self.channels.with_user.return_value = self.channels
        self.channel = self.channels.browse.return_value.exists.return_value
        self.env = Environment({'whatsapp.message': self.messages,
            'product.template': self.products, 'ir.attachment': self.attachments,
            'discuss.channel': self.channels})
        self.env.context = {}

    def run_action(self):
        exec(CODE, {'env': self.env, 'records': self.records, 'datetime': datetime,
                    'log': MagicMock(), 'UserError': UserError})

    def test_images_are_real_attachments_numbered_and_labelled(self):
        self.run_action()
        self.assertEqual(self.attachments.create.call_count, 3)
        self.assertIs(self.attachments.create.call_args_list[0].args[0]['raw'],
                      self.catalog[683].image_1024)
        self.assertEqual(self.channel.message_post.call_count, 4)
        posts = self.channel.message_post.call_args_list
        for i, post in enumerate(posts[:3], 1):
            self.assertEqual(post.kwargs['attachment_ids'], [70])
            self.assertIn('Referensi ' + str(i), post.kwargs['body'])
            self.assertIn('bukan foto hasil produksi', post.kwargs['body'])
            self.assertIn('https://mebel.billbry.id/shop/', post.kwargs['body'])
        self.wa.write.assert_called_once_with({'x_mebel_design_options': '683,682,684'})
        self.assertEqual(self.outgoing.write.call_count, 4)

    def test_wrong_accounts_and_expired_messages_cannot_send(self):
        for field, value in [('account', 3), ('age', 2)]:
            with self.subTest(field=field):
                self.setUp()
                if field == 'account':
                    self.wa.wa_account_id.id = value
                else:
                    self.wa.create_date -= datetime.timedelta(days=value)
                self.run_action()
                self.channel.message_post.assert_not_called()
                self.attachments.create.assert_not_called()

    def test_processed_message_does_not_send_twice(self):
        self.wa.x_mebel_design_options = '683,682,684'
        self.run_action()
        self.channel.message_post.assert_not_called()

    def test_missing_category_asks_before_sending_images(self):
        self.wa.body = 'Boleh lihat gambar?'
        self.run_action()
        self.attachments.create.assert_not_called()
        self.assertIn('meja, kursi', self.channel.message_post.call_args.kwargs['body'])
        self.wa.write.assert_called_once_with({'x_mebel_design_options': '?'})

    def test_recent_context_can_resolve_generic_image_request(self):
        self.wa.body = 'Boleh gambarnya?'
        self.history = [SimpleNamespace(x_mebel_design_options=False, body='Saya ingin meja belajar')]
        self.run_action()
        self.assertEqual(self.attachments.create.call_count, 3)

    def test_category_answer_to_clarifier_sends_gallery(self):
        self.wa.body = 'Meja belajar'
        self.history = [SimpleNamespace(x_mebel_design_options='?', body='Gambar dong')]
        self.run_action()
        self.assertEqual(self.attachments.create.call_count, 3)

    def test_number_selection_preserves_model_without_new_gallery(self):
        self.wa.body = 'Nomor 2'
        self.history = [SimpleNamespace(x_mebel_design_options='683,682,684', body='gambar meja belajar')]
        self.run_action()
        self.attachments.create.assert_not_called()
        self.assertIn('Meja Kerja', self.channel.message_post.call_args.kwargs['body'])
        self.wa.write.assert_called_once_with({'x_mebel_design_options': 'selected:682'})

    def test_negations_complaints_and_ordinary_text_stay_with_ai(self):
        for text in ['Jangan kirim gambar meja', 'Foto meja rusak', 'Berapa harga meja belajar?']:
            with self.subTest(text=text):
                self.setUp()
                self.wa.body = text
                self.run_action()
                self.channel.message_post.assert_not_called()

    def test_customer_own_reference_does_not_trigger_catalog(self):
        for text in ['Kalau gambar dari saya apa bisa kak',
                     'Saya tidak ada yang cocok atau saya kirim gambar saya sarndiri',
                     'Kalau saya boleh mengirimkan gambar sendiri',
                     'Saya punya foto meja belajar', 'Boleh pakai desain sendiri?',
                     'Gambar saya sendiri bisa?', 'Foto sendiri boleh?']:
            with self.subTest(text=text):
                self.setUp()
                self.wa.body = text
                self.run_action()
                self.channel.message_post.assert_not_called()
                self.attachments.create.assert_not_called()

    def test_other_company_products_and_unpublished_images_are_excluded(self):
        for product in self.catalog.values():
            product.company_id.id = 3
        self.run_action()
        self.attachments.create.assert_not_called()
        self.assertIn('belum tersedia', self.channel.message_post.call_args.kwargs['body'])

    def test_specific_unsupported_type_does_not_send_unrelated_table(self):
        self.wa.body = 'Minta gambar meja makan'
        self.run_action()
        self.attachments.create.assert_not_called()
        self.assertIn('belum tersedia', self.channel.message_post.call_args.kwargs['body'])

    def test_dry_run_never_writes_or_sends(self):
        self.env.context = {'mebel_design_dry_run': True}
        self.run_action()
        self.attachments.create.assert_not_called()
        self.channel.message_post.assert_not_called()
        self.wa.write.assert_not_called()

    def test_failure_to_create_native_outbound_is_not_success(self):
        self.messages.search.side_effect = lambda domain, **kw: (
            False if any(x[0] == 'mail_message_id' for x in domain) else self.history)
        with self.assertRaisesRegex(UserError, 'outbound_missing'):
            self.run_action()
        self.wa.write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
