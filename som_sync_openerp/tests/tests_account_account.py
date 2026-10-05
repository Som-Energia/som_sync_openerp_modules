# -*- coding: utf-8 -*-
from destral import testing
from osv import osv
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

    def test_get_endpoint_suffix__returns_false_without_mapping(self):
        account_id = self._account_id()

        suffix = self.account_obj.get_endpoint_suffix(
            self.cursor, self.uid, account_id
        )

        self.assertFalse(suffix)

    @mock.patch.object(odoo_sync.OdooSync, 'syncronize_sync')
    @mock.patch.object(odoo_sync.OdooSync, 'sync_model_enabled_amplified')
    def test_sync_without_odoo_account_code__is_not_started(
            self, mock_enabled, mock_syncronize_sync):
        account_id = self._account_id()
        mock_enabled.return_value = (True, False, False)

        result = self.sync_obj.common_sync_model_create_update(
            self.cursor, self.uid, 'account.account', 'sync', account_id
        )

        self.assertEqual(result, (None, None))
        mock_syncronize_sync.assert_not_called()

    def test_check_special_restrictions__allows_account_with_odoo_account_code(self):
        account_id = self._account_id()
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'odoo_account_code': '700000001',
        })

        result = self.account_obj.check_special_restrictions(
            self.cursor, self.uid, account_id
        )

        self.assertTrue(result)

    def test_create__requires_odoo_account_code(self):
        account_type_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras'
        )[1]

        self.assertRaises(osv.except_osv, self.account_obj.create,
                          self.cursor, self.uid, {
                              'name': 'Account without Odoo code',
                              'code': '700000000001',
                              'type': 'other',
                              'user_type': account_type_id,
                          })

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
