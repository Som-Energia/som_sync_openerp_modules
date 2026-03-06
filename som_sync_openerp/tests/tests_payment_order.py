
# -*- coding: utf-8 -*-
from destral import testing
from destral.patch import PatchNewCursors
import mock
import netsvc
from ..models import odoo_sync


class TestPaymentOrder(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.ai_obj = self.openerp.pool.get("account.invoice")
        self.ail_obj = self.openerp.pool.get("account.invoice.line")
        self.aj_obj = self.openerp.pool.get("account.journal")
        self.imd_obj = self.openerp.pool.get("ir.model.data")
        self.sync_obj = self.openerp.pool.get("odoo.sync")
        self.wf_service = netsvc.LocalService('workflow')
        self.po_obj = self.openerp.pool.get("payment.order")
        self.pl_obj = self.openerp.pool.get("payment.line")
        self.maxDiff = None
        super(TestPaymentOrder, self).setUp()

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_inbound(self, mock_syncronize_sync, mock_erp_id, mock_odoo_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0004"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        odoo_account_id = 99
        odoo_journal_id = 66
        erp_account_id = 1

        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_erp_id.return_value = iva_tax_id
        mock_odoo_id.return_value = odoo_journal_id
        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )
        invoice = self.ai_obj.browse(self.cursor, self.uid, invoice_id)
        # Cercar la línia de receivable dins del moviment comptable
        move_line_id = None
        for line in invoice.move_id.line_id:
            if line.account_id.type == 'receivable':
                move_line_id = line.id
                break
        self.pl_obj.create(self.cursor, self.uid, {
            'order_id': remesa_id,
            'move_line_id': move_line_id,
            'partner_id': invoice.partner_id.id,
            'name': invoice.name or '/',
            'date': invoice.date_invoice,
            'state': 'normal',
            'communication': invoice.name or '/',
            'amount_currency': invoice.amount_total * -1,
            'currency': invoice.currency_id.id,
        })

        related_values = self.po_obj.get_related_values(
            self.cursor, self.uid, remesa_id
        )

        expected_values = {
            'amount': 1000.0,
            'batch_type': 'inbound',
            'journal_destiny': odoo_journal_id,
            'lines': [
                {
                    'amount': 1000.0,
                    'invoice_id': 99,
                }
            ],
            'method_id': 373,
            'name': u'Remesa 0001',
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    @mock.patch.object(odoo_sync.OdooSync, "get_erp_id_by_odoo_id")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_outbound(self, mock_syncronize_sync, mock_erp_id, mock_odoo_id):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0005"
        )[1]
        iva_tax_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_tax_iva"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0002"
        )[1]
        odoo_account_id = 99
        odoo_journal_id = 66
        erp_account_id = 1

        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        mock_erp_id.return_value = iva_tax_id
        mock_odoo_id.return_value = odoo_journal_id
        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )
        invoice = self.ai_obj.browse(self.cursor, self.uid, invoice_id)
        # Cercar la línia de receivable dins del moviment comptable
        move_line_id = None
        for line in invoice.move_id.line_id:
            if line.account_id.type == 'receivable':
                move_line_id = line.id
                break
        self.pl_obj.create(self.cursor, self.uid, {
            'order_id': remesa_id,
            'move_line_id': move_line_id,
            'partner_id': invoice.partner_id.id,
            'name': invoice.name or '/',
            'date': invoice.date_invoice,
            'state': 'normal',
            'communication': invoice.name or '/',
            'amount_currency': invoice.amount_total,
            'currency': invoice.currency_id.id,
        })

        related_values = self.po_obj.get_related_values(
            self.cursor, self.uid, remesa_id
        )

        expected_values = {
            'amount': 1000.0,
            'batch_type': 'outbound',
            'journal_destiny': odoo_journal_id,
            'lines': [
                {
                    'amount': 1000.0,
                    'invoice_id': 99,
                }
            ],
            'method_id': 375,
            'name': u'Remesa 0002',
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    def test__write_triggers_async(self, mock_syncronize_sync, mock_sync_model_enabled_amplified):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0004"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        odoo_account_id = 99
        erp_account_id = 1
        mock_syncronize_sync.return_value = (odoo_account_id, erp_account_id)
        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )
        invoice = self.ai_obj.browse(self.cursor, self.uid, invoice_id)
        # Cercar la línia de receivable dins del moviment comptable
        move_line_id = None
        for line in invoice.move_id.line_id:
            if line.account_id.type == 'receivable':
                move_line_id = line.id
                break
        self.pl_obj.create(self.cursor, self.uid, {
            'order_id': remesa_id,
            'move_line_id': move_line_id,
            'partner_id': invoice.partner_id.id,
            'name': invoice.name or '/',
            'date': invoice.date_invoice,
            'state': 'normal',
            'communication': invoice.name or '/',
            'amount_currency': invoice.amount_total,
            'currency': invoice.currency_id.id,
        })
        # sync_model_enabled_amplified returns (sync_enabled, auto_sync, async_enabled)
        mock_sync_model_enabled_amplified.return_value = (True, True, True)
        # Pay payment order
        self.po_obj.action_open(self.cursor, self.uid, [remesa_id])
        wiz_pay_o = self.openerp.pool.get('pagar.remesa.wizard')
        with PatchNewCursors():
            context = {'active_ids': [remesa_id], 'active_id': remesa_id}
            wiz_pay_id = wiz_pay_o.create(
                self.cursor,
                self.uid,
                {'work_async': False},
                context=context,
            )
            wiz_pay_o.action_pagar_remesa_threaded(self.cursor.dbname, self.uid, [
                                                   wiz_pay_id], context=context)

        mock_syncronize_sync.assert_called_once()
