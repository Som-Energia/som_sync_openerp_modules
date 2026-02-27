# -*- coding: utf-8 -*-
from __future__ import absolute_import
import mock
import time

import netsvc
from destral import testing
from ..models import odoo_sync
from som_sync_openerp.models.odoo_exceptions import (
    CreationNotSupportedException, ERPObjectNotExistsException
)


class TestOdooSync(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.ai_obj = self.openerp.pool.get("account.invoice")
        self.aa_obj = self.openerp.pool.get("account.account")
        self.wf_service = netsvc.LocalService("workflow")
        self.maxDiff = None
        super(TestOdooSync, self).setUp()

    def test_create_odoo_record__notSupported(self):
        with self.assertRaises(CreationNotSupportedException):
            self.sync_obj.create_odoo_record(self.cursor, self.uid, 'res.municipi', {})

    def test_check_erp_record_exist__True(self):
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_asus'
        )[1]

        res = self.sync_obj.check_erp_record_exist(self.cursor, self.uid, 'res.partner', partner_id)

        self.assertEqual(res, True)

    def test_check_erp_record_exist__Exception(self):
        with self.assertRaises(ERPObjectNotExistsException):
            self.sync_obj.check_erp_record_exist(self.cursor, self.uid, 'res.partner', 123456)

    def test___create_sync_record__ok(self):
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_thymbra'
        )[1]
        context = {
            'sync_state': 'synced',
            'update_odoo_created_sync': True,
        }

        sync_id = self.sync_obj._create_sync_record(
            self.cursor, self.uid, 'res.partner', partner_id, 5001, '2024-06-10 12:00:00', context
        )

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertEqual(sync_record.model.model, 'res.partner')
        self.assertEqual(sync_record.res_id, partner_id)
        self.assertEqual(sync_record.odoo_id, 5001)
        self.assertEqual(sync_record.sync_state, 'synced')

    def test___create_sync_record__error(self):
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_thymbra'
        )[1]
        context = {
            'sync_state': 'error',
            'odoo_last_update_result': '{"message": "err", "error_code": "INTERNAL_SERVER_ERROR"}',
            'update_last_sync': True,
        }

        sync_id = self.sync_obj._create_sync_record(
            self.cursor, self.uid, 'res.partner', partner_id, 0, '2024-06-10 12:00:00', context
        )

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertEqual(sync_record.model.model, 'res.partner')
        self.assertEqual(sync_record.res_id, partner_id)
        self.assertEqual(sync_record.odoo_id, 0)
        self.assertEqual(sync_record.sync_state, 'error')

    def test__build_update_vals__syncPartnerAlreadySyncred__ok(self):
        sync_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'odoo_partner_already_syncred'
        )[1]
        context = {
            'sync_state': 'synced',
            'update_last_sync': True,
        }

        vals, update = self.sync_obj._build_update_vals(
            self.cursor, self.uid, sync_id, 1001, '2024-06-10 12:00:00', context
        )

        expected_vals = {
            'odoo_id': 1001,
            'odoo_last_sync_at': '2024-06-10 12:00:00',
            'sync_state': 'synced'
        }
        self.assertEqual(vals, expected_vals)
        self.assertEqual(update, True)

    def test__build_update_vals__syncPartnerAlreadySyncred__okFK(self):
        sync_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'odoo_partner_already_syncred'
        )[1]
        context = {
            'from_fk_sync': True,
        }

        vals, update = self.sync_obj._build_update_vals(
            self.cursor, self.uid, sync_id, 1001, '2024-06-10 12:00:00', context
        )

        expected_vals = {
            'odoo_id': 1001,
        }
        self.assertEqual(vals, expected_vals)
        self.assertEqual(update, False)

    def test__build_update_vals__syncPartnerAlreadySyncred__withError(self):
        sync_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'odoo_partner_already_syncred'
        )[1]
        context = {
            'sync_state': 'error',
            'odoo_last_update_result': '{"message": "err", "error_code": "INTERNAL_SERVER_ERROR"}',
            'update_last_sync': True,
        }

        vals, update = self.sync_obj._build_update_vals(
            self.cursor, self.uid, sync_id, 1001, '2024-06-10 12:00:00', context
        )

        expected_vals = {
            'odoo_id': 1001,
            'odoo_last_sync_at': '2024-06-10 12:00:00',
            'odoo_last_update_result': '{"message": "err", "error_code": "INTERNAL_SERVER_ERROR"}',
            'sync_state': 'error'
        }
        self.assertEqual(vals, expected_vals)
        self.assertEqual(update, True)

    def test__build_update_vals__syncCountryStateError_withOk(self):
        sync_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'odoo_country_state_error'
        )[1]
        context = {
            'sync_state': 'synced',
            'update_last_sync': True,
        }

        vals, update = self.sync_obj._build_update_vals(
            self.cursor, self.uid, sync_id, 1001, '2024-06-10 12:00:00', context
        )

        expected_vals = {
            'odoo_id': 1001,
            'odoo_last_sync_at': '2024-06-10 12:00:00',
            'odoo_last_update_result': '',
            'sync_state': 'synced'
        }
        self.assertEqual(vals, expected_vals)
        self.assertEqual(update, True)

    def test__get_or_create_static_odoo_id__create(self):
        afp_obj = self.openerp.pool.get("account.fiscal.position")
        afp_id = afp_obj.create(self.cursor, self.uid, {'name': 'Test Static AFP'}, context={})

        param_odoo_id = 123
        odoo_id = self.sync_obj.get_or_create_static_odoo_id(
            self.cursor, self.uid, 'account.fiscal.position', afp_id, param_odoo_id, context={}
        )
        self.assertEqual(odoo_id, param_odoo_id)

        os_ids = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.fiscal.position'),
            ('res_id', '=', afp_id),
        ])
        self.assertEqual(len(os_ids), 1)
        os_record = self.sync_obj.browse(self.cursor, self.uid, os_ids[0])
        self.assertEqual(os_record.odoo_id, param_odoo_id)

    def test__get_or_create_static_odoo_id__existing_update(self):
        afp_obj = self.openerp.pool.get("account.fiscal.position")
        afp_id = afp_obj.create(self.cursor, self.uid, {'name': 'Test Static AFP'}, context={})

        param_odoo_id = 123
        odoo_id = self.sync_obj.get_or_create_static_odoo_id(
            self.cursor, self.uid, 'account.fiscal.position', afp_id, param_odoo_id, context={}
        )
        self.assertEqual(odoo_id, param_odoo_id)

        os_ids_1 = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.fiscal.position'),
            ('res_id', '=', afp_id),
        ])
        self.assertEqual(len(os_ids_1), 1)

        param_odoo_id2 = 456
        odoo_id = self.sync_obj.get_or_create_static_odoo_id(
            self.cursor, self.uid, 'account.fiscal.position', afp_id, param_odoo_id2, context={}
        )

        os_ids_2 = self.sync_obj.search(self.cursor, self.uid, [
            ('model.model', '=', 'account.fiscal.position'),
            ('res_id', '=', afp_id),
        ])
        self.assertEqual(len(os_ids_2), 1)
        self.assertEqual(os_ids_1[0], os_ids_2[0])
        self.assertEqual(odoo_id, param_odoo_id2)

    def test__get_or_create_static_odoo_id__just_get(self):
        afp_obj = self.openerp.pool.get("account.fiscal.position")
        afp_id = afp_obj.create(self.cursor, self.uid, {'name': 'Test Static AFP'}, context={})

        param_odoo_id = 123
        odoo_id = self.sync_obj.get_or_create_static_odoo_id(
            self.cursor, self.uid, 'account.fiscal.position', afp_id, param_odoo_id, context={}
        )
        self.assertEqual(odoo_id, param_odoo_id)

        odoo_id = self.sync_obj.get_or_create_static_odoo_id(
            self.cursor, self.uid, 'account.fiscal.position', afp_id, False, context={}
        )
        self.assertEqual(odoo_id, param_odoo_id)

    def test__sync_model_enabled_amplified__setting_ok(self):
        config_obj = self.openerp.pool.get('res.config')
        dict_models_to_sync = eval(
            config_obj.get(self.cursor, self.uid, 'odoo_erp_models_to_sync', '[]'))
        for _dict in dict_models_to_sync:
            self.assertIn('model', _dict)
            self.assertIn('auto_sync', _dict)
            self.assertIn('async_enabled', _dict)
        self.assertIsInstance(dict_models_to_sync, list)

    def test__sync_model_enabled_amplified__enabled_async_disabled_auto(self):
        for model in [
            'account.account',
            'res.country.state',
            'res.country',
            'res.municipi',
            'res.partner',
            'res.partner.address',
            'res.partner.bank'
        ]:
            res = self.sync_obj.sync_model_enabled_amplified(
                self.cursor, self.uid, model
            )

            self.assertEqual(res, (True, False, True))

    def test__sync_model_enabled_amplified__all_enabled(self):
        config_obj = self.openerp.pool.get('res.config')
        config_obj.set(
            self.cursor, self.uid, 'odoo_erp_models_to_sync',
            """[
                {'model': 'account.account', 'auto_sync': True, 'async_enabled': True},
                {'model': 'res.country.state', 'auto_sync': True, 'async_enabled': True},
                {'model': 'res.country', 'auto_sync': True, 'async_enabled': True},
                {'model': 'res.municipi', 'auto_sync': True, 'async_enabled': True},
                {'model': 'res.partner', 'auto_sync': True, 'async_enabled': True},
                {'model': 'res.partner.address', 'auto_sync': True, 'async_enabled': True},
                {'model': 'res.partner.bank', 'auto_sync': True, 'async_enabled': True}
            ]"""
        )
        for model in [
            'account.account',
            'res.country.state',
            'res.country',
            'res.municipi',
            'res.partner',
            'res.partner.address',
            'res.partner.bank'
        ]:
            res = self.sync_obj.sync_model_enabled_amplified(
                self.cursor, self.uid, model
            )

            self.assertEqual(res, (True, True, True))

    def test___clean_context_update_data(self):
        context = {
            'sync_state': 'synced',
            'odoo_last_sync_at': '2024-06-10 12:00:00',
            'odoo_last_update_result': '{"message": "ok", "error_code": "NONE"}',
            'update_last_sync': True,
            'update_odoo_created_sync': True,
            'from_fk_sync': True,
        }

        cleaned_context = self.sync_obj._clean_context_update_data(self.cursor, self.uid, context)

        expected_context = {
            'odoo_last_sync_at': '2024-06-10 12:00:00',
            'from_fk_sync': True,
        }
        self.assertEqual(cleaned_context, expected_context)

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_model_vals_to_sync__partner(self, mock_common_sync_model_create_update):
        mock_common_sync_model_create_update.return_value = (2, 2)
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_asus'
        )[1]

        vals = self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'res.partner', partner_id
        )

        account_41_id = self.aa_obj.search(self.cursor, self.uid, [('code', 'like', '4100%0')])[0]
        account_43_id = self.aa_obj.search(self.cursor, self.uid, [('code', 'like', '4300%0')])[0]
        self.assertEqual(self.sync_obj.common_sync_model_create_update.call_count, 2)
        self.sync_obj.common_sync_model_create_update.assert_has_calls([
            mock.call(mock.ANY, self.uid, 'account.account', 'sync',
                      account_43_id, {'from_fk_sync': True}),
            mock.call(mock.ANY, self.uid, 'account.account', 'sync',
                      account_41_id, {'from_fk_sync': True}),
        ])
        expected_vals = {
            'is_company': True,
            'is_customer': True,
            'is_supplier': True,
            'lang': False,
            'name': u'ASUStek',
            'pnt_erp_id': mock.ANY,
            'property_account_payable_id': 2,
            'property_account_position_id': None,
            'property_account_receivable_id': 2,
            'property_inbound_payment_method_line_id': None,
            'property_outbound_payment_method_line_id': None,
            'property_payment_term_id': None,
            'type': 'contact',
            'vat': u'S2903826B'
        }
        self.assertEqual(vals, expected_vals)

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_model_vals_to_sync__partner_address(self, mock_common_sync_model_create_update):
        mock_common_sync_model_create_update.return_value = (3, 3)
        address_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_address_8'
        )[1]

        vals = self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'res.partner.address', address_id
        )

        self.assertEqual(self.sync_obj.common_sync_model_create_update.call_count, 1)
        self.sync_obj.common_sync_model_create_update.assert_has_calls([
            mock.call(mock.ANY, self.uid, 'res.partner', 'sync', 3, {'from_fk_sync': True}),
        ])
        expected_vals = {
            'city': u'Wavre',
            'email': '',
            'is_company': False,
            'is_customer': True,
            'is_supplier': False,
            'lang': False,
            'name': u'Sylvie Lelitre',
            'parent_id': 3,
            'phone': u'555123456',
            'pnt_erp_id': 10,
            'state_id': None,
            'street': u'69 rue de Chimay',
            'type': 'invoice',
            'zip': u'5478'
        }
        self.assertEqual(vals, expected_vals)

    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_model_vals_to_sync__invoice(self, mock_syncronize_sync, mock_erp_id):
        mock_syncronize_sync.return_value = (2, 2)
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        mock_erp_id.return_value = iva_tax_id
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'invoice_0001'
        )[1]

        vals = self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'account.invoice', invoice_id
        )

        expected_vals = {
            'amount_tax': 0.0,
            'amount_total': 1000.0,
            'amount_untaxed': 1000.0,
            'date': '2026-01-16',
            'fiscal_position_id': None,
            'invoice_date': '2026-01-16',
            'invoice_line_ids': [{
                'account_id': 2,
                'extra_operations_erp': 1,
                'name': 'Agrupaci\xc3\xb3 163500',
                'price_unit': 1000.0,
                'quantity': 1,
                'quantity_erp': 1,
            }],
            'invoice_payment_term_id': None,
            'journal_id': 2,
            'move_type': u'out_invoice',
            'number': u'INV0001',
            'partner_id': 2,
            'pnt_erp_id': invoice_id,
            'preferred_payment_method_line_id': None,
            'ref': '',
        }
        self.assertEqual(vals, expected_vals)

    def test__get_dict_to_patch(self):
        erp_data = {
            'name': 'Test Name modified',
            'active': True,
            'parent_id': 5,
            'country_id': None,
        }
        odoo_record = {
            'id': 10,
            'name': 'Test Name',
            'active': True,
            'parent_id': [5, 'Parent Name'],
            'country_id': False,
        }

        dict_to_patch = self.sync_obj.get_dict_to_patch(
            self.cursor, self.uid, erp_data, odoo_record)

        modified_fields = {
            'name': 'Test Name modified',
        }
        self.assertEqual(dict_to_patch, modified_fields)

    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__common_sync_model_create_update_draft_invoice(self, mock_syncronize_sync):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'invoice_0001'
        )[1]

        self.sync_obj.common_sync_model_create_update(
            self.cursor, self.uid, 'account.invoice', 'sync', invoice_id, {})

        mock_syncronize_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__common_sync_model_create_update_open_invoice(
            self, mock_syncronize_sync, mock_sync_model_enabled_amplified):
        mock_sync_model_enabled_amplified.return_value = (True, True, True)
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'invoice_0001'
        )[1]
        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )

        self.sync_obj.common_sync_model_create_update(
            self.cursor, self.uid, 'account.invoice', 'sync', invoice_id, {})

        # Check 2 calls to syncronize.
        # Open invoice (write) and sync (common_sync_model_create_update)
        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 2)
        self.sync_obj.syncronize_sync.assert_has_calls([
            mock.call(mock.ANY, self.uid, u'account.invoice', 'create',
                      invoice_id, context={'update_last_sync': True}),
            mock.call(mock.ANY, self.uid, u'account.invoice', 'sync',
                      invoice_id, context={'update_last_sync': True}),
        ])

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__common_sync_model_create_update_paid_invoice(
            self, mock_syncronize_sync, mock_sync_model_enabled_amplified):
        mock_sync_model_enabled_amplified.return_value = (True, True, True)
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'invoice_0001'
        )[1]
        month = 'period_{0}'.format(int(time.strftime('%m')))
        period_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'account', month
        )[1]
        account_id = self.aa_obj.search(self.cursor, self.uid, [('code', '=', '570000')])[0]
        journal_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'account_journal_sales_syncronizable'
        )[1]
        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )
        self.ai_obj.pay_and_reconcile(
            self.cursor, self.uid, invoice_id, 1000,
            account_id, period_id, journal_id, account_id, period_id, journal_id
        )

        self.sync_obj.common_sync_model_create_update(
            self.cursor, self.uid, 'account.invoice', 'sync', invoice_id, {})

        # Check 3 calls to syncronize.
        # Open invoice (write), Pay invoice (write) and sync (common_sync_model_create_update)
        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 3)
        self.sync_obj.syncronize_sync.assert_has_calls([
            mock.call(mock.ANY, self.uid, u'account.invoice', 'create',
                      invoice_id, context={'update_last_sync': True}),
            mock.call(mock.ANY, self.uid, u'account.invoice', 'create',
                      invoice_id, context={'update_last_sync': True}),
            mock.call(mock.ANY, self.uid, u'account.invoice', 'sync',
                      invoice_id, context={'update_last_sync': True}),
        ])

    @mock.patch.object(odoo_sync.OdooSync, "update_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "create_odoo_record")
    @mock.patch.object(odoo_sync.OdooSync, "exists_in_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "get_model_vals_to_sync")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__syncronize_sync__create_record_patched_api(
            self, mock_sync_model_enabled_amplified, mock_get_model_vals_to_sync,
            mock_exists_in_odoo, mock_create_odoo_record, mock_update_odoo_id):
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_asus'
        )[1]
        mock_sync_model_enabled_amplified.return_value = (True, True, False)
        mock_get_model_vals_to_sync.return_value = {
            'pnt_erp_id': partner_id,
            'name': u'ASUStek',
        }
        mock_exists_in_odoo.return_value = (False, False, False)
        mock_create_odoo_record.return_value = (4321, '')

        odoo_id, erp_id = self.sync_obj.syncronize_sync(
            self.cursor, self.uid, 'res.partner', 'sync', partner_id, context={}
        )

        self.assertEqual(odoo_id, 4321)
        self.assertEqual(erp_id, partner_id)
        mock_create_odoo_record.assert_called_once_with(
            mock.ANY, self.uid, 'res.partner',
            {'pnt_erp_id': partner_id, 'name': u'ASUStek'}, context={}
        )
        mock_update_odoo_id.assert_called_once_with(
            mock.ANY, self.uid, 'res.partner', partner_id, 4321, context=mock.ANY
        )

    @mock.patch.object(odoo_sync.OdooSync, "update_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "update_odoo_record")
    @mock.patch.object(odoo_sync.OdooSync, "get_dict_to_patch")
    @mock.patch.object(odoo_sync.OdooSync, "exists_in_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "get_model_vals_to_sync")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__syncronize_sync__update_record_patched_api(
            self, mock_sync_model_enabled_amplified, mock_get_model_vals_to_sync,
            mock_exists_in_odoo, mock_get_dict_to_patch, mock_update_odoo_record,
            mock_update_odoo_id):
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_asus'
        )[1]
        mock_sync_model_enabled_amplified.return_value = (True, True, False)
        mock_get_model_vals_to_sync.return_value = {
            'pnt_erp_id': partner_id,
            'name': u'ASUStek',
        }
        mock_exists_in_odoo.return_value = (9999, partner_id, {'name': u'Old'})
        mock_get_dict_to_patch.return_value = {'name': u'ASUStek'}
        mock_update_odoo_record.return_value = (True, '')

        odoo_id, erp_id = self.sync_obj.syncronize_sync(
            self.cursor, self.uid, 'res.partner', 'write', partner_id, context={}
        )

        self.assertEqual(odoo_id, 9999)
        self.assertEqual(erp_id, partner_id)
        mock_update_odoo_record.assert_called_once_with(
            mock.ANY, self.uid, 'res.partner', 9999, partner_id,
            {'name': u'ASUStek'}, {}
        )
        mock_update_odoo_id.assert_called_once_with(
            mock.ANY, self.uid, 'res.partner', partner_id, 9999, context=mock.ANY
        )

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "get_or_create_static_odoo_id")
    def test__syncronize_sync__static_model(
            self, mock_get_or_create_static_odoo_id, mock_sync_model_enabled_amplified):
        afp_obj = self.openerp.pool.get("account.fiscal.position")
        afp_id = afp_obj.create(self.cursor, self.uid, {'name': 'Test Static AFP 2'}, context={})
        mock_get_or_create_static_odoo_id.return_value = 777

        odoo_id, erp_id = self.sync_obj.syncronize_sync(
            self.cursor, self.uid, 'account.fiscal.position', 'sync', afp_id,
            context={'odoo_id': 777}
        )

        self.assertEqual(odoo_id, 777)
        self.assertEqual(erp_id, afp_id)
        mock_get_or_create_static_odoo_id.assert_called_once_with(
            mock.ANY, self.uid, 'account.fiscal.position', afp_id, 777, {'odoo_id': 777}
        )
        mock_sync_model_enabled_amplified.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "get_model_vals_to_sync")
    @mock.patch.object(odoo_sync.OdooSync, "exists_in_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__syncronize_sync__from_fk_sync_shortcut(
            self, mock_sync_model_enabled_amplified, mock_get_odoo_id_by_erp_id,
            mock_exists_in_odoo, mock_get_model_vals_to_sync):
        account_id = self.aa_obj.search(
            self.cursor, self.uid, [('code', 'like', '4300%0')])[0]
        mock_sync_model_enabled_amplified.return_value = (True, True, False)
        mock_get_odoo_id_by_erp_id.return_value = 555

        odoo_id, erp_id = self.sync_obj.syncronize_sync(
            self.cursor, self.uid, 'account.account', 'sync', account_id,
            context={'from_fk_sync': True}
        )

        self.assertEqual(odoo_id, 555)
        self.assertEqual(erp_id, account_id)
        mock_get_odoo_id_by_erp_id.assert_called_once_with(
            mock.ANY, self.uid, 'account.account', account_id
        )
        mock_exists_in_odoo.assert_not_called()
        mock_get_model_vals_to_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "update_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "create_odoo_record")
    @mock.patch.object(odoo_sync.OdooSync, "get_model_vals_to_sync")
    @mock.patch.object(odoo_sync.OdooSync, "exists_in_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    def test__syncronize_sync__no_from_fk_sync(
            self, mock_sync_model_enabled_amplified, mock_get_odoo_id_by_erp_id,
            mock_exists_in_odoo, mock_get_model_vals_to_sync,
            mock_create_odoo_record, mock_update_odoo_id):
        account_id = self.aa_obj.search(
            self.cursor, self.uid, [('code', 'like', '4300%0')])[0]
        mock_sync_model_enabled_amplified.return_value = (True, True, False)
        mock_exists_in_odoo.return_value = (False, False, False)
        mock_get_model_vals_to_sync.return_value = {
            'pnt_erp_id': account_id,
            'code': u'4300TEST',
            'name': u'Account Test'
        }
        mock_create_odoo_record.return_value = (321, '')

        odoo_id, erp_id = self.sync_obj.syncronize_sync(
            self.cursor, self.uid, 'account.account', 'sync', account_id, context={}
        )

        self.assertEqual(odoo_id, 321)
        self.assertEqual(erp_id, account_id)
        mock_get_odoo_id_by_erp_id.assert_not_called()
        mock_exists_in_odoo.assert_called_once()
        mock_get_model_vals_to_sync.assert_called_once_with(
            mock.ANY, self.uid, 'account.account', account_id, context={}
        )
        mock_create_odoo_record.assert_called_once_with(
            mock.ANY, self.uid, 'account.account',
            {'pnt_erp_id': account_id, 'code': u'4300TEST', 'name': u'Account Test'},
            context={}
        )
        mock_update_odoo_id.assert_called_once_with(
            mock.ANY, self.uid, 'account.account', account_id, 321, context=mock.ANY
        )


class TestOdooUrlRecord(testing.OOTestCaseWithCursor):
    """Test cases for odoo_url_record computed field"""

    def setUp(self):
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        super(TestOdooUrlRecord, self).setUp()

    def test_odoo_url_record__no_model(self):
        """Test odoo_url_record returns False when model is not set"""
        # Create sync record without model
        sync_id = self.sync_obj.create(self.cursor, self.uid, {
            'res_id': 1,
            'odoo_id': 100,
            'sync_state': 'synced',
        }, context={})

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertFalse(sync_record.odoo_url_record)

    def test_odoo_url_record__no_res_id(self):
        """Test odoo_url_record returns False when res_id is not set"""
        ir_model_obj = self.openerp.pool.get("ir.model")
        model_id = ir_model_obj.search(
            self.cursor, self.uid, [('model', '=', 'res.partner')], limit=1
        )[0]

        sync_id = self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id,
            'odoo_id': 100,
            'sync_state': 'synced',
        }, context={})

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertFalse(sync_record.odoo_url_record)

    def test_odoo_url_record__no_odoo_id(self):
        """Test odoo_url_record returns False when odoo_id is not set"""
        ir_model_obj = self.openerp.pool.get("ir.model")
        model_id = ir_model_obj.search(
            self.cursor, self.uid, [('model', '=', 'res.partner')], limit=1
        )[0]

        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_thymbra'
        )[1]

        sync_id = self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id,
            'res_id': partner_id,
            'sync_state': 'synced',
        }, context={})

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertFalse(sync_record.odoo_url_record)

    def test_odoo_url_record__partner_with_valid_data(self):
        """Test odoo_url_record returns correct URL for res.partner"""
        ir_model_obj = self.openerp.pool.get("ir.model")
        model_id = ir_model_obj.search(
            self.cursor, self.uid, [('model', '=', 'res.partner')], limit=1
        )[0]

        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_thymbra'
        )[1]

        odoo_id = 160440
        sync_id = self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id,
            'res_id': partner_id,
            'odoo_id': odoo_id,
            'sync_state': 'synced',
        }, context={})

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        # Expected: http://odoo_url/odoo/contacts/160440
        # Note: odoo_url is extracted from res.config 'odoo_url_api'
        self.assertIsNotNone(sync_record.odoo_url_record)
        self.assertIn('/odoo/contacts/{}'.format(odoo_id), sync_record.odoo_url_record)

    def test_odoo_url_record__with_mock_odoo_url_api(self):
        """Test odoo_url_record builds correct URL from odoo_url_api config"""
        self.openerp.pool.get("res.config")

        # Mock the _get_conn_params method to return a specific URL
        with mock.patch.object(
            self.sync_obj, '_get_conn_params'
        ) as mock_get_conn:
            mock_get_conn.return_value = ('http://localhost:8069/api/v1', 'test_key')

            ir_model_obj = self.openerp.pool.get("ir.model")
            model_id = ir_model_obj.search(
                self.cursor, self.uid, [('model', '=', 'res.partner')], limit=1
            )[0]

            partner_id = self.imd_obj.get_object_reference(
                self.cursor, self.uid, 'base', 'res_partner_thymbra'
            )[1]

            odoo_id = 160440
            sync_id = self.sync_obj.create(self.cursor, self.uid, {
                'model': model_id,
                'res_id': partner_id,
                'odoo_id': odoo_id,
                'sync_state': 'synced',
            }, context={})

            sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
            # Expected: http://localhost:8069/odoo/contacts/160440
            expected_url = 'http://localhost:8069/odoo/contacts/{}'.format(odoo_id)
            self.assertEqual(sync_record.odoo_url_record, expected_url)

    def test_odoo_url_record__model_without_endpoint_method(self):
        """Test odoo_url_record returns False for models without get_endpoint_odoo_record_suffix"""
        ir_model_obj = self.openerp.pool.get("ir.model")
        # res.country model doesn't have get_endpoint_odoo_record_suffix method
        model_id = ir_model_obj.search(
            self.cursor, self.uid, [('model', '=', 'res.country')], limit=1
        )[0]

        sync_id = self.sync_obj.create(self.cursor, self.uid, {
            'model': model_id,
            'res_id': 1,
            'odoo_id': 200,
            'sync_state': 'synced',
        }, context={})

        sync_record = self.sync_obj.browse(self.cursor, self.uid, sync_id)
        self.assertFalse(sync_record.odoo_url_record)

    def test_format_response(self):
        response = {
            'message': 'Error message',
            'error_code': 'ERROR_CODE',
        }
        formatted_response = self.sync_obj.format_response(response)
        expected_formatted_response = '{\n  "message": "Error message", \n  "error_code": "ERROR_CODE"\n}'  # noqa: E501
        self.assertEqual(formatted_response, expected_formatted_response)

        response = 'Not a dict'
        formatted_response = self.sync_obj.format_response(response)
        expected_formatted_response = 'Not a dict'
        self.assertEqual(formatted_response, expected_formatted_response)

        response = '{"success": false, "message": "Validation error in request parameters", "error_code": "INVALID_PARAMETERS", "data": {"validation_errors": [{"type": "extra_forbidden", "loc": ["vat"], "msg": "Extra inputs are not permitted", "input": "PS123456789\u00a0"}]}}'  # noqa: E501
        formatted_response = self.sync_obj.format_response(response)
        expected_formatted_response = u'{\n  "data": {\n    "validation_errors": [\n      {\n        "msg": "Extra inputs are not permitted", \n        "loc": [\n          "vat"\n        ], \n        "type": "extra_forbidden", \n        "input": "PS123456789\xa0"\n      }\n    ]\n  }, \n  "message": "Validation error in request parameters", \n  "error_code": "INVALID_PARAMETERS", \n  "success": false\n}'  # noqa: E501
        self.assertEqual(expected_formatted_response, formatted_response)
