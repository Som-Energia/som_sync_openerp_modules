# -*- coding: utf-8 -*-
from addons import get_module_resource
from destral import testing
from lxml import etree
import mock
from osv import osv
from tools.translate import trans_load


class TestAccountDuplicationTranslations(testing.OOTestCaseWithCursor):

    def setUp(self):
        super(TestAccountDuplicationTranslations, self).setUp()
        self.wizard_obj = self.openerp.pool.get('wizard.duplicate.account')
        self.account_obj = self.openerp.pool.get('account.account')
        self.imd_obj = self.openerp.pool.get('ir.model.data')
        self.context = {'lang': 'ca_ES'}
        trans_load(self.cursor, get_module_resource(
            'som_sync_openerp', 'i18n', 'ca_ES.po'
        ), 'ca_ES')

    def test_wizard_and_account_field_labels_are_translated(self):
        fields = self.wizard_obj.fields_get(
            self.cursor, self.uid, ['account_id', 'code', 'line_ids'],
            context=self.context,
        )
        self.assertEqual(fields['account_id']['string'], u"Compte d'origen")
        self.assertEqual(fields['code']['string'], u'Codi del compte nou')
        self.assertEqual(fields['line_ids']['string'], u'Comptes fills')
        account_fields = self.account_obj.fields_get(
            self.cursor, self.uid, ['odoo_account_code'], context=self.context
        )
        self.assertEqual(account_fields['odoo_account_code']['string'],
                         u"Codi del compte d'Odoo")

    def test_wizard_view_and_action_are_translated(self):
        view_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'view_wizard_duplicate_account'
        )[1]
        view = self.wizard_obj.fields_view_get(
            self.cursor, self.uid, view_id=view_id, view_type='form', context=self.context
        )
        document = etree.fromstring(view['arch'])
        self.assertEqual(document.get('string'), u'Duplica un compte')
        self.assertEqual(document.xpath('//button[@name="action_duplicate"]')[0].get('string'),
                         u'Crea el compte')
        action_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'action_wizard_duplicate_account'
        )[1]
        action = self.openerp.pool.get('ir.actions.act_window').read(
            self.cursor, self.uid, action_id, ['name'], context=self.context
        )
        self.assertEqual(action['name'], u'Duplica un compte...')

    def test_helper_error_uses_language_context_and_preserves_placeholder(self):
        # Gettext opens a separate read cursor. Route it to this transaction so
        # it can see the catalog loaded above without committing test data.
        with mock.patch('pooler.get_db_only') as get_db:
            get_db.return_value.cursor.return_value.__enter__.return_value = self.cursor
            with self.assertRaises(osv.except_osv) as caught:
                self.wizard_obj._confirmed_codes(
                    self.cursor, self.uid, mock.Mock(code='700000001'), False, False,
                    context=self.context,
                )

        self.assertEqual(caught.exception.value,
                         u'Indiqueu un codi nou per al compte 700000001.')

    def test_copy_guard_error_is_translated(self):
        account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'account', 'account_unpaid'
        )[1]
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'odoo_account_code': '700000001',
        })

        with mock.patch('pooler.get_db_only') as get_db:
            get_db.return_value.cursor.return_value.__enter__.return_value = self.cursor
            with self.assertRaises(osv.except_osv) as caught:
                self.account_obj.copy(
                    self.cursor, self.uid, account_id, context=self.context
                )

        self.assertEqual(caught.exception.value,
                         u'Utilitzeu l\'acció "Duplica un compte..." per confirmar els codis '
                         u'del compte nou abans de crear-lo i sincronitzar-lo.')

    def test_helper_keeps_english_for_english_context(self):
        with mock.patch('pooler.get_db_only') as get_db:
            get_db.return_value.cursor.return_value.__enter__.return_value = self.cursor
            with self.assertRaises(osv.except_osv) as caught:
                self.wizard_obj._confirmed_codes(
                    self.cursor, self.uid, mock.Mock(code='700000001'), False, False,
                    context={'lang': 'en_US'},
                )

        self.assertEqual(caught.exception.value,
                         'Specify a new code for account 700000001.')
