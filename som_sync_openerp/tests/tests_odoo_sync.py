# -*- coding: utf-8 -*-
from __future__ import absolute_import
from mock import MagicMock, call, ANY

from destral import testing
from som_sync_openerp.models.odoo_exceptions import (
    CreationNotSupportedException, ERPObjectNotExistsException
)


class TestOdooSync(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
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

    def test__get_model_vals_to_sync__partner(self):
        # Ensure the mocked syncronize_sync returns a 2-tuple (odoo_id, erp_id)
        # so the caller can unpack it without raising ValueError.
        self.sync_obj.syncronize_sync = MagicMock(return_value=(2, 2))
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'base', 'res_partner_asus'
        )[1]

        vals = self.sync_obj.get_model_vals_to_sync(
            self.cursor, self.uid, 'res.partner', partner_id
        )

        self.assertEqual(self.sync_obj.syncronize_sync.call_count, 2)
        self.sync_obj.syncronize_sync.assert_has_calls([
            call(ANY, self.uid, u'account.account', 'sync', 2, {'from_fk_sync': True}),
            call(ANY, self.uid, u'account.account', 'sync', 3, {'from_fk_sync': True}),
        ])
        expected_vals = {
            'is_company': True,
            'is_customer': True,
            'is_supplier': True,
            'lang': False,
            'name': u'ASUStek',
            'pnt_erp_id': 2,
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
