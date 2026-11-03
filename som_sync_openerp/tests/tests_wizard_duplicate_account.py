# -*- coding: utf-8 -*-
from destral import testing
import mock
from osv import osv

from ..models import odoo_sync


class TestWizardDuplicateAccount(testing.OOTestCaseWithCursor):

    def setUp(self):
        super(TestWizardDuplicateAccount, self).setUp()
        self.account_obj = self.openerp.pool.get('account.account')
        self.wizard_obj = self.openerp.pool.get('wizard.duplicate.account')
        self.sync_obj = self.openerp.pool.get('odoo.sync')
        self.source_id = self.openerp.pool.get('ir.model.data').get_object_reference(
            self.cursor, self.uid, 'account', 'account_unpaid'
        )[1]
        self.account_obj.write(self.cursor, self.uid, [self.source_id], {
            'odoo_account_code': '700000001',
        })
        self.context = {
            'active_model': 'account.account', 'active_ids': [self.source_id],
        }

    def _create_wizard(self, **values):
        defaults = self.wizard_obj.default_get(
            self.cursor, self.uid,
            ['account_id', 'name', 'code', 'odoo_account_code', 'has_children', 'line_ids'],
            context=self.context,
        )
        defaults.update(values)
        return self.wizard_obj.create(
            self.cursor, self.uid, defaults, context=self.context
        )

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_open_and_cancel_do_not_create_or_sync_accounts(self, mock_sync):
        account_ids = self.account_obj.search(self.cursor, self.uid, [])

        wizard_id = self._create_wizard()
        wizard = self.wizard_obj.browse(self.cursor, self.uid, wizard_id)

        self.assertEqual(wizard.account_id.id, self.source_id)
        self.assertEqual(wizard.name, wizard.account_id.name)
        self.assertFalse(wizard.code)
        self.assertFalse(wizard.odoo_account_code)
        # Cancel closes the transient form without calling action_duplicate.
        self.assertEqual(
            self.account_obj.search(self.cursor, self.uid, []), account_ids
        )
        mock_sync.assert_not_called()

    def test_defaults_require_exactly_one_source_account(self):
        for active_ids in ([], [self.source_id, self.source_id]):
            self.assertRaises(
                osv.except_osv, self.wizard_obj.default_get,
                self.cursor, self.uid, ['account_id'],
                context={'active_model': 'account.account',
                         'active_ids': active_ids},
            )

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_standard_copy_is_blocked_even_with_context_flag(self, mock_sync):
        self.assertRaises(
            osv.except_osv, self.account_obj.copy,
            self.cursor, self.uid, self.source_id,
            context={'allow_account_copy': True},
        )
        mock_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_standard_copy_of_twelve_digit_account_without_mapping_is_blocked(
            self, mock_sync):
        self.cursor.execute(
            'UPDATE account_account SET code = %s, odoo_account_code = NULL '
            'WHERE id = %s', ('700000000001', self.source_id),
        )

        self.assertRaises(
            osv.except_osv, self.account_obj.copy,
            self.cursor, self.uid, self.source_id,
        )

        mock_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_standard_copy_without_mapping_keeps_legacy_behavior(self, mock_sync):
        self.account_obj.write(self.cursor, self.uid, [self.source_id], {
            'code': '700000001', 'odoo_account_code': False,
        })

        new_id = self.account_obj.copy(self.cursor, self.uid, self.source_id)

        account = self.account_obj.browse(self.cursor, self.uid, new_id)
        self.assertEqual(account.code, '700000001(copy)')
        self.assertFalse(account.odoo_account_code)
        self.assertEqual(mock_sync.call_count, 1)

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_confirm_creates_and_syncs_only_final_values(self, mock_sync):
        tax_id = self.openerp.pool.get('ir.model.data').get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_tax_iva'
        )[1]
        self.account_obj.write(self.cursor, self.uid, [self.source_id], {
            'note': 'Keep the source account configuration',
            'reconcile': True, 'check_history': False, 'shortcut': 'COPYTEST',
            'tax_ids': [(6, 0, [tax_id])],
        })
        model_id = self.openerp.pool.get('ir.model').search(
            self.cursor, self.uid, [('model', '=', 'account.account')]
        )[0]
        link_id = self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id, 'res_id': self.source_id, 'sync_state': 'synced',
        })
        link_before = self.sync_obj.read(
            self.cursor, self.uid, link_id, ['res_id', 'sync_state']
        )
        fields = ['name', 'code', 'odoo_account_code', 'company_id',
                  'user_type', 'type', 'parent_id', 'currency_mode', 'reconcile',
                  'note', 'check_history', 'shortcut', 'tax_ids', 'currency_id']
        source_before = self.account_obj.read(
            self.cursor, self.uid, self.source_id, fields
        )
        wizard_id = self._create_wizard(
            name='Duplicated account', code='700000000002',
            odoo_account_code='700000002',
        )
        mock_sync.assert_not_called()

        action = self.wizard_obj.action_duplicate(
            self.cursor, self.uid, [wizard_id], context=self.context
        )

        new_id = action['res_id']
        self.assertNotEqual(new_id, self.source_id)
        account = self.account_obj.read(self.cursor, self.uid, new_id, fields)
        self.assertEqual(account['name'], 'Duplicated account')
        self.assertEqual(account['code'], '700000000002')
        self.assertEqual(account['odoo_account_code'], '700000002')
        for field in fields[3:]:
            self.assertEqual(account[field], source_before[field])
        self.assertEqual(self.account_obj.read(
            self.cursor, self.uid, self.source_id, fields
        ), source_before)
        self.assertEqual(self.sync_obj.read(
            self.cursor, self.uid, link_id, ['res_id', 'sync_state']
        ), link_before)
        mock_sync.assert_called_once_with(
            self.cursor, self.uid, 'account.account', 'create', new_id,
            context=self.context,
        )
        self.assertNotIn('account_copy_defaults', self.context)

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_wizard_uses_copy_and_translation_hooks(self, mock_sync):
        wizard_id = self._create_wizard(code='700000000002',
                                        odoo_account_code='700000002')
        with mock.patch.object(self.account_obj, 'copy',
                               wraps=self.account_obj.copy) as copy_hook:
            with mock.patch.object(self.account_obj, 'copy_translations',
                                   wraps=self.account_obj.copy_translations) as translations_hook:
                action = self.wizard_obj.action_duplicate(
                    self.cursor, self.uid, [wizard_id], context=self.context
                )

        self.assertEqual(copy_hook.call_count, 1)
        self.assertEqual(translations_hook.call_count, 1)
        self.assertEqual(translations_hook.call_args[0][2:4],
                         (self.source_id, action['res_id']))
        excluded = translations_hook.call_args[0][4]['copy_translations_excluded']
        self.assertNotIn('name', excluded)
        self.assertEqual(excluded['code'], '700000000002')

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_copy_extension_defaults_are_preserved(self, mock_sync):
        wizard_id = self._create_wizard(code='700000000002',
                                        odoo_account_code='700000002')
        original_copy = self.account_obj.copy

        def copy_with_extension(cr, uid, account_id, default=None, context=None, **kwargs):
            defaults = dict(default or {})
            defaults['note'] = 'Configured by a copy extension'
            return original_copy(cr, uid, account_id, default=defaults,
                                 context=context, **kwargs)

        with mock.patch.object(self.account_obj, 'copy', side_effect=copy_with_extension):
            action = self.wizard_obj.action_duplicate(
                self.cursor, self.uid, [wizard_id], context=self.context
            )

        account = self.account_obj.browse(self.cursor, self.uid, action['res_id'])
        self.assertEqual(account.note, 'Configured by a copy extension')
        self.assertEqual(account.code, '700000000002')
        self.assertEqual(account.odoo_account_code, '700000002')

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_translatable_configuration_is_copied(self, mock_sync):
        self.account_obj.write(self.cursor, self.uid, [self.source_id], {
            'note': 'Account configuration',
        })
        language_obj = self.openerp.pool.get('res.lang')
        language_ids = language_obj.search(self.cursor, self.uid, [('code', '=', 'en_US')])
        language_obj.write(self.cursor, self.uid, language_ids, {'translatable': True})
        translation_obj = self.openerp.pool.get('ir.translation')
        translation_obj.create(self.cursor, self.uid, {
            'name': 'account.account,note', 'type': 'model', 'lang': 'en_US',
            'res_id': self.source_id, 'src': 'Account configuration',
            'value': 'Translated account configuration',
        })
        wizard_id = self._create_wizard(code='700000000002',
                                        odoo_account_code='700000002')

        # An installed extension may make account configuration translatable.
        with mock.patch.object(self.account_obj._columns['note'], 'translate', True):
            action = self.wizard_obj.action_duplicate(
                self.cursor, self.uid, [wizard_id], context=self.context
            )

        translation_ids = translation_obj.search(self.cursor, self.uid, [
            ('name', '=', 'account.account,note'),
            ('res_id', '=', action['res_id']), ('lang', '=', 'en_US'),
        ])
        self.assertEqual(len(translation_ids), 1)
        self.assertEqual(translation_obj.read(
            self.cursor, self.uid, translation_ids[0], ['value']
        )['value'], 'Translated account configuration')

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_explicit_shared_mapping_is_allowed_and_becomes_immutable(
            self, mock_sync):
        wizard_id = self._create_wizard(
            code='700000000002', odoo_account_code='700000001',
        )
        action = self.wizard_obj.action_duplicate(
            self.cursor, self.uid, [wizard_id], context=self.context
        )
        new_id = action['res_id']
        model_id = self.openerp.pool.get('ir.model').search(
            self.cursor, self.uid, [('model', '=', 'account.account')]
        )[0]
        self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id, 'res_id': new_id, 'sync_state': 'synced',
        })

        self.assertRaises(
            osv.except_osv, self.account_obj.write,
            self.cursor, self.uid, [new_id], {'odoo_account_code': '700000002'},
        )

        self.assertEqual(self.account_obj.browse(
            self.cursor, self.uid, new_id
        ).odoo_account_code, '700000001')

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_twelve_digit_code_requires_mapping_before_sync(self, mock_sync):
        wizard_id = self._create_wizard(code='700000000002')

        self.assertRaises(
            osv.except_osv, self.wizard_obj.action_duplicate,
            self.cursor, self.uid, [wizard_id], context=self.context,
        )

        mock_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_nine_digit_code_does_not_inherit_mapping(self, mock_sync):
        wizard_id = self._create_wizard(code='700000002')

        action = self.wizard_obj.action_duplicate(
            self.cursor, self.uid, [wizard_id], context=self.context
        )

        account = self.account_obj.browse(
            self.cursor, self.uid, action['res_id']
        )
        self.assertFalse(account.odoo_account_code)
        self.assertEqual(self.account_obj.get_endpoint_suffix(
            self.cursor, self.uid, account.id
        ), '700000002')

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_children_are_duplicated_with_their_own_confirmed_values(self, mock_sync):
        parent_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'Original parent', 'code': '700000004', 'type': 'view',
            'user_type': self.account_obj.browse(
                self.cursor, self.uid, self.source_id
            ).user_type.id,
        })
        child_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'Original child', 'code': '700000003', 'type': 'other',
            'user_type': self.account_obj.browse(
                self.cursor, self.uid, self.source_id
            ).user_type.id,
            'parent_id': parent_id,
            'odoo_account_code': '700000003',
        })
        mock_sync.reset_mock()
        self.context['active_ids'] = [parent_id]
        wizard_id = self._create_wizard(name='Duplicated parent', code='700000002')
        wizard = self.wizard_obj.browse(self.cursor, self.uid, wizard_id)
        self.assertTrue(wizard.has_children)
        self.assertEqual([line.account_id.id for line in wizard.line_ids], [child_id])
        line = wizard.line_ids[0]
        self.assertFalse(line.code)
        self.assertFalse(line.odoo_account_code)
        self.openerp.pool.get('wizard.duplicate.account.line').write(
            self.cursor, self.uid, [line.id], {
                'code': '700000000006', 'odoo_account_code': '700000006',
            }
        )

        synced_values = []

        def capture_sync(cr, uid, model, action, account_id, context=None):
            account = self.account_obj.browse(cr, uid, account_id)
            synced_values.append((account.code, account.odoo_account_code))

        mock_sync.side_effect = capture_sync

        action = self.wizard_obj.action_duplicate(
            self.cursor, self.uid, [wizard_id], context=self.context
        )

        new_account = self.account_obj.browse(
            self.cursor, self.uid, action['res_id']
        )
        self.assertEqual(len(new_account.child_parent_ids), 1)
        new_child = new_account.child_parent_ids[0]
        self.assertNotEqual(new_child.id, child_id)
        self.assertEqual(new_child.parent_id.id, new_account.id)
        self.assertEqual(new_child.name, 'Original child')
        self.assertEqual(new_child.code, '700000000006')
        self.assertEqual(new_child.odoo_account_code, '700000006')
        self.assertEqual(self.account_obj.browse(
            self.cursor, self.uid, child_id
        ).parent_id.id, parent_id)
        self.assertEqual(synced_values, [
            ('700000000006', '700000006'), ('700000002', False),
        ])

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_incomplete_child_confirmation_is_rejected_before_any_copy(self, mock_sync):
        parent_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'Original parent', 'code': '700000004', 'type': 'view',
            'user_type': self.account_obj.browse(
                self.cursor, self.uid, self.source_id
            ).user_type.id,
        })
        self.account_obj.create(self.cursor, self.uid, {
            'name': 'Original child', 'code': '700000003', 'type': 'other',
            'user_type': self.account_obj.browse(
                self.cursor, self.uid, self.source_id
            ).user_type.id,
            'parent_id': parent_id,
        })
        self.context['active_ids'] = [parent_id]
        wizard_id = self._create_wizard(code='700000002')
        mock_sync.reset_mock()

        self.assertRaises(
            osv.except_osv, self.wizard_obj.action_duplicate,
            self.cursor, self.uid, [wizard_id], context=self.context,
        )

        mock_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_changed_child_list_requires_reopening_before_any_copy(self, mock_sync):
        wizard_id = self._create_wizard(code='700000002')
        child_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'New child', 'code': '700000003', 'type': 'other',
            'user_type': self.account_obj.browse(
                self.cursor, self.uid, self.source_id
            ).user_type.id,
        })
        self.account_obj.write(self.cursor, self.uid, [self.source_id], {
            'child_consol_ids': [(6, 0, [child_id])],
        })
        mock_sync.reset_mock()

        self.assertRaises(
            osv.except_osv, self.wizard_obj.action_duplicate,
            self.cursor, self.uid, [wizard_id], context=self.context,
        )

        mock_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_consolidation_links_are_preserved_like_standard_copy(self, mock_sync):
        self.account_obj.write(self.cursor, self.uid, [self.source_id], {
            'child_consol_ids': [(6, 0, [])],
        })
        child_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'Consolidated child', 'code': '700000003', 'type': 'other',
            'user_type': self.account_obj.browse(
                self.cursor, self.uid, self.source_id
            ).user_type.id,
        })
        self.account_obj.write(self.cursor, self.uid, [self.source_id], {
            'child_consol_ids': [(6, 0, [child_id])],
        })
        wizard_id = self._create_wizard(code='700000002')
        wizard = self.wizard_obj.browse(self.cursor, self.uid, wizard_id)
        self.assertEqual([line.account_id.id for line in wizard.line_ids], [child_id])
        self.openerp.pool.get('wizard.duplicate.account.line').write(
            self.cursor, self.uid, [wizard.line_ids[0].id], {'code': '700000006'}
        )

        action = self.wizard_obj.action_duplicate(
            self.cursor, self.uid, [wizard_id], context=self.context
        )

        account = self.account_obj.browse(self.cursor, self.uid, action['res_id'])
        self.assertEqual([child.id for child in account.child_consol_ids], [child_id])
        self.assertEqual([child.code for child in account.child_parent_ids], ['700000006'])
