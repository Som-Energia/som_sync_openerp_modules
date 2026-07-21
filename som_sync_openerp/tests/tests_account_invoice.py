
# -*- coding: utf-8 -*-
import json
import mock
import netsvc

from destral import testing
from ..models import odoo_sync
from oorq import decorators as oorq_decorators
from oorq.oorq import AsyncMode


class TestAccountInvoice(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.ai_obj = self.openerp.pool.get("account.invoice")
        self.ail_obj = self.openerp.pool.get("account.invoice.line")
        self.aj_obj = self.openerp.pool.get("account.journal")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        self.wf_service = netsvc.LocalService('workflow')
        self.maxDiff = None
        super(TestAccountInvoice, self).setUp()

    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values(self, mock_syncronize_sync, mock_erp_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0001"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_erp_id.return_value = iva_tax_id

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, invoice_id
        )

        expected_values = {
            'amount_tax': 0.0,
            'amount_untaxed': 1000.0,
            'amount_total': 1000.0,
            'date': '2026-01-16',
            'move_type': 'out_invoice',
            'invoice_line_ids': [
                {
                    'account_id': odoo_account_id,
                    'extra_operations_erp': 1,
                    'name': 'Agrupaci\xc3\xb3 1635',
                    'price_unit': 1000.0,
                    'quantity': 1,
                    'quantity_erp': 1,
                }
            ],
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_negative_out_invoice(self, mock_syncronize_sync, mock_erp_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0003"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_erp_id.return_value = iva_tax_id

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, invoice_id
        )

        expected_values = {
            'amount_tax': -0.0,
            'amount_untaxed': 1000.0,
            'amount_total': 1000.0,
            'date': '2026-01-16',
            'move_type': 'out_refund',
            'invoice_line_ids': [
                {
                    'account_id': odoo_account_id,
                    'extra_operations_erp': 1,
                    'name': 'Agrupaci\xc3\xb3 1635',
                    'price_unit': -1000.0,
                    'quantity': -1,
                    'quantity_erp': 1,
                }
            ],
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_negative_out_refund_invoice(
            self, mock_syncronize_sync, mock_erp_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0003"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_erp_id.return_value = iva_tax_id
        self.ai_obj.write(self.cursor, self.uid, [invoice_id], {'type': 'out_refund'})

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, invoice_id
        )

        expected_values = {
            'amount_tax': -0.0,
            'amount_untaxed': 1000.0,
            'amount_total': 1000.0,
            'date': '2026-01-16',
            'move_type': 'out_invoice',
            'invoice_line_ids': [
                {
                    'account_id': odoo_account_id,
                    'extra_operations_erp': 1,
                    'name': 'Agrupaci\xc3\xb3 1635',
                    'price_unit': -1000.0,
                    'quantity': -1,
                    'quantity_erp': 1,
                }
            ],
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_negative_in_refund_invoice(
            self, mock_syncronize_sync, mock_erp_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0003"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_erp_id.return_value = iva_tax_id
        self.ai_obj.write(self.cursor, self.uid, [invoice_id], {'type': 'in_refund'})

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, invoice_id
        )

        expected_values = {
            'amount_tax': -0.0,
            'amount_untaxed': 1000.0,
            'amount_total': 1000.0,
            'date': '2026-01-16',
            'move_type': 'in_invoice',
            'invoice_line_ids': [
                {
                    'account_id': odoo_account_id,
                    'extra_operations_erp': 1,
                    'name': 'Agrupaci\xc3\xb3 1635',
                    'price_unit': -1000.0,
                    'quantity': -1,
                    'quantity_erp': 1,
                }
            ],
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_negative_in_invoice(self, mock_syncronize_sync, mock_erp_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0003"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_erp_id.return_value = iva_tax_id
        self.ai_obj.write(self.cursor, self.uid, [invoice_id], {'type': 'in_invoice'})

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, invoice_id
        )

        expected_values = {
            'amount_tax': 0.0,
            'amount_untaxed': 1000.0,
            'amount_total': 1000.0,
            'date': '2026-01-16',
            'move_type': 'in_refund',
            'invoice_line_ids': [
                {
                    'account_id': odoo_account_id,
                    'extra_operations_erp': 1,
                    'name': 'Agrupaci\xc3\xb3 1635',
                    'price_unit': -1000.0,
                    'quantity': -1,
                    'quantity_erp': 1,
                }
            ],
            'ref': '',
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_with_taxes(self, mock_syncronize_sync, mock_odoo_id, mock_erp_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0002"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_odoo_id.return_value = odoo_account_id
        mock_erp_id.return_value = iva_tax_id
        self.ai_obj.button_reset_taxes(self.cursor, self.uid, [invoice_id])
        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, invoice_id
        )

        expected_values = {
            'date': '2026-01-16',
            'amount_tax': 420.0,
            'amount_untaxed': 4102.2,
            'amount_total': 4522.2,
            'move_type': 'out_invoice',
            'invoice_line_ids': [
                {
                    'account_id': 99,
                    'extra_operations_erp': 1,
                    'name': u'Import IESE',
                    'price_unit': 102.2,
                    'quantity': 1,
                    'quantity_erp': 1,
                    'tax_ids': [99],
                },
                {
                    'account_id': 99,
                    'name': 'Agrupaci\xc3\xb3 1635',
                    'price_unit': 2000.0,
                    'quantity': 1,
                    'quantity_erp': 1,
                    'extra_operations_erp': 1,
                }, {
                    'account_id': 99,
                    'name': 'Agrupaci\xc3\xb3 1635',
                    'price_unit': 2000.0,
                    'quantity': 1,
                    'quantity_erp': 1,
                    'extra_operations_erp': 1,
                    'tax_ids': [99],
                },
            ],
        }
        self.assertEqual(related_values, expected_values)
        self.sync_obj.common_sync_model_create_update.assert_has_calls([
        ])

    def test__journal_is_syncrozable_True(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0001"
        )[1]

        is_syncrozable = self.ai_obj._journal_is_syncrozable(
            self.cursor, self.uid, invoice_id
        )

        self.assertTrue(is_syncrozable)

    def test__journal_is_syncrozable_False(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "account", "invoice_0001"
        )[1]

        is_syncrozable = self.ai_obj._journal_is_syncrozable(
            self.cursor, self.uid, invoice_id
        )

        self.assertFalse(is_syncrozable)

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__write_triggers_async(self, mock_syncronize_sync, mock_sync_model_enabled_amplified):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0001"
        )[1]
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        mock_sync_model_enabled_amplified.return_value = (True, True, True)

        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )

        mock_syncronize_sync.assert_called_once()

    @mock.patch.object(oorq_decorators, 'set_hash_job')
    @mock.patch.object(oorq_decorators.ProcessJobs, 'add_job')
    @mock.patch.object(oorq_decorators.Job, 'create')
    @mock.patch.object(oorq_decorators, 'Queue')
    @mock.patch.object(oorq_decorators, 'setup_redis_connection')
    def test__syncronize_waits_for_commit(
            self, mock_redis_connection, mock_queue, mock_job_create,
            mock_add_job, mock_set_hash_job):
        job = mock.MagicMock()
        mock_job_create.return_value = job

        with AsyncMode(mode='async'):
            self.sync_obj.syncronize(
                self.cursor, self.uid, 'account.invoice', 'create', 1
            )

        mock_add_job.assert_called_once_with(
            id(self.cursor), job, mock_queue.return_value, False
        )

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__write_no_triggers_async_journal_disabled_sync(
            self, mock_syncronize_sync, mock_sync_model_enabled_amplified):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0001"
        )[1]
        invoice = self.ai_obj.browse(self.cursor, self.uid, invoice_id)
        self.aj_obj.write(self.cursor, self.uid, [invoice.journal_id.id], {
                          'som_sync_odoo_invoices': False})

        mock_sync_model_enabled_amplified.return_value = (True, True, True)

        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )

        mock_syncronize_sync.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__write__autosync_not_enabled_no_trigger(
            self, mock_syncronize_sync, mock_sync_model_enabled_amplified):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0001"
        )[1]
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        mock_sync_model_enabled_amplified.return_value = (True, False, True)

        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )

        mock_syncronize_sync.assert_not_called()

    def test__hook_last_modifications(self):
        input_data = {
            'move_type': u'out_invoice',
            'preferred_payment_method_line_id': 400,
            'invoice_payment_term_id': 123,
            'ref': 'INVXXX',
        }
        result_data = {
            'move_type': u'out_invoice',
            'preferred_payment_method_line_id': 400,
            'invoice_payment_term_id': 123,
            'ref': 'INVXXX',
        }
        hook_data = self.ai_obj.hook_last_modifications(
            self.cursor, self.uid, input_data
        )

        self.assertEqual(hook_data, result_data)

        input_data = {
            'move_type': u'in_invoice',
            'preferred_payment_method_line_id': 400,
            'invoice_payment_term_id': 123,
            'ref': False,
        }
        result_data = {
            'move_type': u'in_invoice',
            'preferred_payment_method_line_id': 375,
            'invoice_payment_term_id': 123,
            'ref': False,
        }

        hook_data = self.ai_obj.hook_last_modifications(
            self.cursor, self.uid, input_data
        )

        self.assertEqual(hook_data, result_data)

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__hook_last_modifications_sets_default_payment_term(
            self, mock_get_odoo_id_by_erp_id):
        mock_get_odoo_id_by_erp_id.return_value = 999
        config_obj = self.openerp.pool.get('res.config')
        config_obj.set(self.cursor, self.uid, 'odoo_default_erp_payment_term', '15')
        input_data = {
            'move_type': u'out_invoice',
            'preferred_payment_method_line_id': 400,
            'invoice_payment_term_id': False,
            'ref': 'INVXXX',
        }

        hook_data = self.ai_obj.hook_last_modifications(
            self.cursor, self.uid, input_data
        )

        self.assertEqual(hook_data['invoice_payment_term_id'], 999)
        mock_get_odoo_id_by_erp_id.assert_called_once_with(
            self.cursor, self.uid, 'account.payment.term', 15)

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__hook_last_modifications_keeps_payment_term_when_mapping_missing(
            self, mock_get_odoo_id_by_erp_id):
        mock_get_odoo_id_by_erp_id.return_value = False
        config_obj = self.openerp.pool.get('res.config')
        config_obj.set(self.cursor, self.uid, 'odoo_default_erp_payment_term', '15')
        input_data = {
            'move_type': u'out_invoice',
            'preferred_payment_method_line_id': 400,
            'invoice_payment_term_id': False,
            'ref': 'INVXXX',
        }

        hook_data = self.ai_obj.hook_last_modifications(
            self.cursor, self.uid, input_data
        )

        self.assertFalse(hook_data['invoice_payment_term_id'])

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__hook_last_modifications_keeps_payment_term_when_default_not_configured(
            self, mock_get_odoo_id_by_erp_id):
        config_obj = self.openerp.pool.get('res.config')
        config_obj.set(self.cursor, self.uid, 'odoo_default_erp_payment_term', '0')
        input_data = {
            'move_type': u'out_invoice',
            'preferred_payment_method_line_id': 400,
            'invoice_payment_term_id': False,
            'ref': 'INVXXX',
        }

        hook_data = self.ai_obj.hook_last_modifications(
            self.cursor, self.uid, input_data
        )

        self.assertFalse(hook_data['invoice_payment_term_id'])
        mock_get_odoo_id_by_erp_id.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__hook_last_modifications_does_not_override_payment_term(
            self, mock_get_odoo_id_by_erp_id):
        input_data = {
            'move_type': u'out_invoice',
            'preferred_payment_method_line_id': 400,
            'invoice_payment_term_id': 123,
            'ref': 'INVXXX',
        }

        hook_data = self.ai_obj.hook_last_modifications(
            self.cursor, self.uid, input_data
        )

        self.assertEqual(hook_data['invoice_payment_term_id'], 123)
        mock_get_odoo_id_by_erp_id.assert_not_called()

    def test__hook_after_odoo_creation_with_discrepancies(self):
        """
        Test hook_after_odoo_creation with amount discrepancies above tolerance
        Should set sync_state to 'error'
        """
        response = {
            'data': {
                'metadata': [{
                    'pnt_amount_untaxed_erp_difference': 10.50,
                    'pnt_amount_tax_erp_difference': 2.21,
                    'pnt_amount_total_erp_difference': 12.71,
                    'pnt_amount_untaxed_erp_discrepancy': True,
                    'pnt_amount_tax_erp_discrepancy': False,
                    'pnt_amount_total_erp_discrepancy': True,
                }]
            }
        }
        sync_vals = {'sync_state': 'synced'}

        self.ai_obj.hook_after_odoo_creation(
            self.cursor, self.uid, response, sync_vals
        )

        self.assertEqual(sync_vals['sync_state'], 'error')

    def test__hook_after_odoo_creation_with_discrepancies_as_string(self):
        """
        Test hook_after_odoo_creation with response as JSON string and difference above tolerance
        Should set sync_state to 'error'
        """

        response = json.dumps({
            'data': {
                'metadata': [{
                    'pnt_amount_untaxed_erp_difference': 5.0,
                    'pnt_amount_tax_erp_difference': 1.05,
                    'pnt_amount_total_erp_difference': 6.05,
                    'pnt_amount_untaxed_erp_discrepancy': False,
                    'pnt_amount_tax_erp_discrepancy': True,
                    'pnt_amount_total_erp_discrepancy': False,
                }]
            }
        })
        sync_vals = {'sync_state': 'synced'}

        self.ai_obj.hook_after_odoo_creation(
            self.cursor, self.uid, response, sync_vals
        )

        self.assertEqual(sync_vals['sync_state'], 'error')

    def test__hook_after_odoo_creation_without_discrepancies(self):
        """
        Test hook_after_odoo_creation without any discrepancies
        Should NOT modify sync_state
        """
        response = {
            'data': {
                'metadata': [{
                    'pnt_amount_untaxed_erp_difference': 0.0,
                    'pnt_amount_tax_erp_difference': 0.0,
                    'pnt_amount_total_erp_difference': 0.0,
                    'pnt_amount_untaxed_erp_discrepancy': False,
                    'pnt_amount_tax_erp_discrepancy': False,
                    'pnt_amount_total_erp_discrepancy': False,
                }]
            }
        }
        sync_vals = {'sync_state': 'synced'}

        self.ai_obj.hook_after_odoo_creation(
            self.cursor, self.uid, response, sync_vals
        )

        self.assertEqual(sync_vals['sync_state'], 'synced')

    def test__hook_after_odoo_creation_difference_within_tolerance(self):
        """
        Test hook_after_odoo_creation with difference within tolerance
        Should set sync_state to 'synced_with_warning'
        """
        response = {
            'data': {
                'metadata': [{
                    'pnt_amount_total_erp_difference': 0.01,
                }]
            }
        }
        sync_vals = {'sync_state': 'synced'}

        self.ai_obj.hook_after_odoo_creation(
            self.cursor, self.uid, response, sync_vals
        )

        self.assertEqual(sync_vals['sync_state'], 'synced_with_warning')

    def test__hook_after_odoo_creation_difference_above_tolerance(self):
        """
        Test hook_after_odoo_creation with difference above tolerance
        Should set sync_state to 'error'
        """
        response = {
            'data': {
                'metadata': [{
                    'pnt_amount_total_erp_difference': 0.03,
                }]
            }
        }
        sync_vals = {'sync_state': 'synced'}

        self.ai_obj.hook_after_odoo_creation(
            self.cursor, self.uid, response, sync_vals
        )

        self.assertEqual(sync_vals['sync_state'], 'error')

    def test__hook_after_odoo_creation_difference_exactly_at_tolerance(self):
        """
        Test hook_after_odoo_creation with difference exactly at tolerance boundary
        Should set sync_state to 'synced_with_warning'
        """
        response = {
            'data': {
                'metadata': [{
                    'pnt_amount_total_erp_difference': 0.02,
                }]
            }
        }
        sync_vals = {'sync_state': 'synced'}

        self.ai_obj.hook_after_odoo_creation(
            self.cursor, self.uid, response, sync_vals
        )

        self.assertEqual(sync_vals['sync_state'], 'synced_with_warning')
