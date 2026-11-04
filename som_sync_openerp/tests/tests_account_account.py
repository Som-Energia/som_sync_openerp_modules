# -*- coding: utf-8 -*-
from destral import testing
from osv import osv
from osv.orm import FieldsValidationException
import mock

from ..models import odoo_sync


class TestAccountAccount(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.account_obj = self.openerp.pool.get('account.account')
        self.sync_obj = self.openerp.pool.get('odoo.sync')
        self.imd_obj = self.openerp.pool.get('ir.model.data')
        super(TestAccountAccount, self).setUp()

    def _account_id(self):
        return self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'account', 'account_unpaid'
        )[1]

    def _link_account_to_odoo(self, account_id):
        model_id = self.openerp.pool.get('ir.model').search(
            self.cursor, self.uid, [('model', '=', 'account.account')], limit=1
        )[0]
        self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id,
            'res_id': account_id,
            'sync_state': 'synced',
        })

    def test_write__odoo_account_code_cannot_change_when_linked(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'odoo_account_code': '700000001',
        })
        self._link_account_to_odoo(account_id)

        self.assertRaises(
            osv.except_osv, self.account_obj.write,
            self.cursor, self.uid, [account_id], {
                'odoo_account_code': '700000002',
            }
        )

    def test_write__same_odoo_account_code_is_allowed_when_linked(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'odoo_account_code': '700000001',
        })
        self._link_account_to_odoo(account_id)

        result = self.account_obj.write(self.cursor, self.uid, [account_id], {
            'odoo_account_code': '700000001',
        })

        self.assertTrue(result)

    def test_write__odoo_account_code_can_change_when_not_linked(self):
        account_id = self._account_id()

        result = self.account_obj.write(self.cursor, self.uid, [account_id], {
            'odoo_account_code': '700000001',
        })

        self.assertTrue(result)

    def test_get_endpoint_suffix__uses_explicit_odoo_account_code(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000000001',
            'odoo_account_code': '700000001',
        })

        suffix = self.account_obj.get_endpoint_suffix(
            self.cursor, self.uid, account_id
        )

        self.assertEqual(suffix, '700000001')

    def test_get_model_vals_to_sync__uses_explicit_odoo_account_code(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000000001',
            'odoo_account_code': '700000001',
        })

        vals = self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'account.account', account_id
        )

        self.assertEqual(vals['code'], '700000001')
        self.assertNotIn('odoo_account_code', vals)

    def test_get_endpoint_suffix__falls_back_to_account_code_without_mapping(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000001',
            'odoo_account_code': False,
        })

        suffix = self.account_obj.get_endpoint_suffix(
            self.cursor, self.uid, account_id
        )

        self.assertEqual(suffix, '700000001')

    def test_get_model_vals_to_sync__falls_back_to_account_code_without_mapping(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000001',
            'odoo_account_code': False,
        })

        vals = self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'account.account', account_id
        )

        self.assertEqual(vals['code'], '700000001')
        self.assertNotIn('odoo_account_code', vals)

    @mock.patch.object(odoo_sync.OdooSync, 'syncronize_sync')
    @mock.patch.object(odoo_sync.OdooSync, 'sync_model_enabled_amplified')
    def test_sync_with_twelve_digit_code_without_mapping__is_not_started(
            self, mock_enabled, mock_syncronize_sync):
        account_id = self._account_id()
        self.cursor.execute(
            'UPDATE account_account SET code = %s, odoo_account_code = NULL WHERE id = %s',
            ('700000000001', account_id),
        )
        mock_enabled.return_value = (True, False, False)

        result = self.sync_obj.common_sync_model_create_update(
            self.cursor, self.uid, 'account.account', 'sync', account_id
        )

        self.assertEqual(result, (None, None))
        mock_syncronize_sync.assert_not_called()

    def test_create_with_twelve_digit_code_without_mapping__is_rejected(self):
        account_type_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras'
        )[1]

        self.assertRaises(FieldsValidationException, self.account_obj.create,
                          self.cursor, self.uid, {
                              'name': 'Account without Odoo code',
                              'code': '700000000001',
                              'type': 'other',
                              'user_type': account_type_id,
                          })

    def test_write_with_twelve_digit_code_without_mapping__is_rejected(self):
        account_id = self._account_id()

        self.assertRaises(FieldsValidationException, self.account_obj.write,
                          self.cursor, self.uid, [account_id], {
                              'code': '700000000001',
                              'odoo_account_code': False,
                          })

    def test_check_special_restrictions__allows_nine_digit_account_without_mapping(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000001',
            'odoo_account_code': False,
        })

        result = self.account_obj.check_special_restrictions(
            self.cursor, self.uid, account_id
        )

        self.assertTrue(result)

    def test_check_special_restrictions__allows_twelve_digit_account_with_mapping(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000000001',
            'odoo_account_code': '700000001',
        })

        result = self.account_obj.check_special_restrictions(
            self.cursor, self.uid, account_id
        )

        self.assertTrue(result)

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_create__excluded_groups_do_not_start_sync(self, mock_sync):
        account_type_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras'
        )[1]
        for code in ('200000001', '500000001'):
            account_id = self.account_obj.create(self.cursor, self.uid, {
                'name': 'Excluded account',
                'code': code,
                'type': 'other',
                'user_type': account_type_id,
            })

            self.assertTrue(account_id)
            self.assertFalse(self.sync_obj.search(self.cursor, self.uid, [
                ('model.model', '=', 'account.account'),
                ('res_id', '=', account_id),
            ]))
        mock_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_create__non_excluded_group_starts_sync(self, mock_sync):
        account_type_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras'
        )[1]
        account_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'Synchronized account',
            'code': '700000002',
            'type': 'other',
            'user_type': account_type_id,
        })

        mock_sync.assert_called_once_with(
            self.cursor, self.uid, 'account.account', 'create', account_id, context={}
        )

    def test_excluded_account_groups__configuration_is_installed(self):
        model, config_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'odoo_sync_excluded_account_groups'
        )
        self.assertEqual(model, 'res.config')
        config = self.openerp.pool.get(model).read(
            self.cursor, self.uid, config_id, ['name', 'value']
        )
        self.assertEqual(config['name'], 'odoo_sync_excluded_account_groups')
        self.assertEqual(config['value'], '2,5')

    def test_is_sync_excluded__uses_erp_group_and_configured_groups(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '400000000001',
            'odoo_account_code': '200000001',
        })
        config_obj = self.openerp.pool.get('res.config')
        for groups, expected in [('2,5', False), (' 4, 7 ', True), ('', False)]:
            config_obj.set(self.cursor, self.uid, 'odoo_sync_excluded_account_groups', groups)

            self.assertEqual(self.account_obj.is_sync_excluded(
                self.cursor, self.uid, account_id
            ), expected)

        self.account_obj.write(self.cursor, self.uid, [account_id], {'code': '200000001'})
        self.assertFalse(self.account_obj.is_sync_excluded(
            self.cursor, self.uid, account_id
        ))

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_ensure_demo_account_iva__reuses_existing_account(self, mock_sync):
        before_count = len(self.account_obj.search(
            self.cursor, self.uid, [('code', '=', '475600'), ('company_id', '=', 1)]
        ))

        ensured_id = self.account_obj.ensure_demo_account_iva(
            self.cursor, self.uid, odoo_account_code='000475600', context={}
        )

        account_ids = self.account_obj.search(
            self.cursor, self.uid, [('code', '=', '475600'), ('company_id', '=', 1)]
        )

        self.assertTrue(ensured_id in account_ids)
        self.assertEqual(len(account_ids), before_count)

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_ensure_demo_account_iva__creates_missing_account(self, mock_sync):
        account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_account_iva'
        )[1]
        imd_id = self.imd_obj._get_id(
            self.cursor, self.uid, 'som_sync_openerp', 'account_account_iva'
        )
        self.imd_obj.unlink(self.cursor, self.uid, [imd_id])
        self.account_obj.unlink(self.cursor, self.uid, [account_id])

        ensured_id = self.account_obj.ensure_demo_account_iva(
            self.cursor, self.uid, odoo_account_code='000475600', context={}
        )
        xml_account_id = self.imd_obj.read(
            self.cursor, self.uid,
            self.imd_obj.search(
                self.cursor, self.uid,
                [('module', '=', 'som_sync_openerp'), ('name', '=', 'account_account_iva')],
                limit=1
            )[0],
            ['res_id']
        )['res_id']
        account = self.account_obj.read(
            self.cursor, self.uid, ensured_id,
            ['name', 'code', 'company_id', 'currency_mode', 'type', 'odoo_account_code']
        )

        self.assertEqual(xml_account_id, ensured_id)
        self.assertEqual(account['name'], 'Compte IVA per linia IESE')
        self.assertEqual(account['code'], '475600')
        self.assertEqual(account['odoo_account_code'], '000475600')
        self.assertEqual(account['company_id'][0], 1)
        self.assertEqual(account['currency_mode'], 'current')
        self.assertEqual(account['type'], 'other')
