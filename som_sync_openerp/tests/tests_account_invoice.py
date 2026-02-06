
# -*- coding: utf-8 -*-
from destral import testing
import mock
import netsvc
from ..models import odoo_sync


class TestAccountInvoice(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.ai_obj = self.openerp.pool.get("account.invoice")
        self.aj_obj = self.openerp.pool.get("account.journal")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        self.wf_service = netsvc.LocalService('workflow')
        super(TestAccountInvoice, self).setUp()

    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__get_related_values(self, mock_syncronize_sync):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0001"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)

        related_values = self.ai_obj.get_related_values(
            self.cursor, self.uid, invoice_id
        )

        expected_values = {
            'date': '2026-01-16',
            'invoice_line_ids': [
                {
                    'account_id': odoo_account_id,
                    'name': u'Product A',
                    'price_unit': 1000.0,
                    'quantity': 1.0,
                    'quantity_erp': 1.0
                }
            ]
        }
        self.assertEqual(related_values, expected_values)

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
