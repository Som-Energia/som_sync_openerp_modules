# -*- coding: utf-8 -*-
from destral import testing
import mock

from ..models import account_account
from ..models import odoo_sync


class TestAccountAccount(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.account_obj = self.openerp.pool.get("account.account")
        self.conf_obj = self.openerp.pool.get("res.config")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestAccountAccount, self).setUp()

    def test_get_endpoint_suffix(self):
        account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "account", "account_unpaid"
        )[1]

        suffix = self.account_obj.get_endpoint_suffix(self.cursor, self.uid, account_id)

        self.assertEqual(suffix, '412345')

    def test__normalize_account_code_for_odoo__returns_original_when_config_empty(self):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', ''
        )

        normalized = self.account_obj._normalize_account_code_for_odoo(
            self.cursor, self.uid, '700000000103'
        )

        self.assertEqual(normalized, '700000000103')

    def test__normalize_account_code_for_odoo__reduces_middle_zeroes(self):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', '9'
        )

        normalized = self.account_obj._normalize_account_code_for_odoo(
            self.cursor, self.uid, '700000000103'
        )

        self.assertEqual(normalized, '700000103')

    def test__normalize_account_code_for_odoo__uses_configured_target_length(self):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', '8'
        )

        normalized = self.account_obj._normalize_account_code_for_odoo(
            self.cursor, self.uid, '700000000103'
        )

        self.assertEqual(normalized, '70000103')

    @mock.patch.object(account_account.logger, 'warning')
    def test__normalize_account_code_for_odoo__warns_when_not_reducible(
            self, mock_warning):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', '9'
        )

        normalized = self.account_obj._normalize_account_code_for_odoo(
            self.cursor, self.uid, '700123456789'
        )

        self.assertEqual(normalized, '700123456789')
        mock_warning.assert_called_once_with(
            'Cannot normalize account code %s to target length %s '
            'without removing non-zero middle digits',
            '700123456789', 9,
        )

    def test__get_endpoint_suffix__returns_normalized_code_when_enabled(self):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', '9'
        )
        account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "account", "account_unpaid"
        )[1]
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000000103',
        })

        suffix = self.account_obj.get_endpoint_suffix(
            self.cursor, self.uid, account_id
        )

        self.assertEqual(suffix, '700000103')

    def test__get_model_vals_to_sync__normalizes_code_when_enabled(self):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', '9'
        )
        account_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "account", "account_unpaid"
        )[1]
        self.account_obj.write(self.cursor, self.uid, [account_id], {
            'code': '700000000103',
        })

        vals = self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'account.account', account_id
        )

        self.assertEqual(vals['code'], '700000103')

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    @mock.patch.object(account_account.logger, 'warning')
    def test__normalize_account_code_for_odoo__keeps_original_when_normalized_code_exists(
            self, mock_warning, mock_sync):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', '9'
        )
        account_type_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras'
        )[1]
        source_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'Long ERP account',
            'code': '700000000103',
            'type': 'other',
            'user_type': account_type_id,
        })
        self.account_obj.create(self.cursor, self.uid, {
            'name': 'Existing normalized account',
            'code': '700000103',
            'type': 'other',
            'user_type': account_type_id,
        })

        normalized = self.account_obj._normalize_account_code_for_odoo(
            self.cursor, self.uid, '700000000103', account_id=source_id
        )

        self.assertEqual(normalized, '700000000103')
        mock_warning.assert_called_once_with(
            'Cannot normalize account code %s to %s because account %s already uses that code',
            '700000000103', '700000103', mock.ANY,
        )

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test__normalize_account_code_for_odoo__returns_normalized_when_no_existing_short_code(
            self, mock_sync):
        self.conf_obj.set(
            self.cursor, self.uid,
            'odoo_sync_account_code_normalized_length', '9'
        )
        account_type_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'financieras'
        )[1]
        source_id = self.account_obj.create(self.cursor, self.uid, {
            'name': 'Long ERP account',
            'code': '700000000103',
            'type': 'other',
            'user_type': account_type_id,
        })
        self.account_obj.create(self.cursor, self.uid, {
            'name': 'Different account',
            'code': '701000103',
            'type': 'other',
            'user_type': account_type_id,
        })

        normalized = self.account_obj._normalize_account_code_for_odoo(
            self.cursor, self.uid, '700000000103', account_id=source_id
        )

        self.assertEqual(normalized, '700000103')

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test_ensure_demo_account_iva__reuses_existing_account(self, mock_sync):
        before_count = len(self.account_obj.search(
            self.cursor, self.uid, [('code', '=', '475600'), ('company_id', '=', 1)]
        ))

        ensured_id = self.account_obj.ensure_demo_account_iva(
            self.cursor, self.uid, context={}
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
            self.cursor, self.uid, context={}
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
            ['name', 'code', 'company_id', 'currency_mode', 'type']
        )

        self.assertEqual(xml_account_id, ensured_id)
        self.assertEqual(account['name'], 'Compte IVA per linia IESE')
        self.assertEqual(account['code'], '475600')
        self.assertEqual(account['company_id'][0], 1)
        self.assertEqual(account['currency_mode'], 'current')
        self.assertEqual(account['type'], 'other')
