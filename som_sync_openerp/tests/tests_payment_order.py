
# -*- coding: utf-8 -*-
from destral import testing
from destral.patch import PatchNewCursors
import mock
import netsvc
from ..models import odoo_sync
import unittest


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

    def utils_open_invoice_add_to_order(self, invoice_id, order_id, factor=1):
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
            'order_id': order_id,
            'move_line_id': move_line_id,
            'partner_id': invoice.partner_id.id,
            'name': invoice.name or '/',
            'date': invoice.date_invoice,
            'state': 'normal',
            'communication': invoice.name or '/',
            'amount_currency': invoice.amount_total * factor,
            'currency': invoice.currency_id.id,
        })

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
        self.utils_open_invoice_add_to_order(invoice_id, remesa_id, factor=-1)

        related_values = self.po_obj.get_related_values(
            self.cursor, self.uid, remesa_id
        )

        expected_values = {
            'amount': 1000.0,
            'batch_type': 'inbound',
            'destination_journal_id': odoo_journal_id,
            'lines': [
                {
                    'amount': 1000.0,
                    'invoice_id': 99,
                }
            ],
            'payment_method_id': 373,
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
        self.utils_open_invoice_add_to_order(invoice_id, remesa_id)

        related_values = self.po_obj.get_related_values(
            self.cursor, self.uid, remesa_id
        )

        expected_values = {
            'amount': 1000.0,
            'batch_type': 'outbound',
            'destination_journal_id': odoo_journal_id,
            'lines': [
                {
                    'amount': 1000.0,
                    'invoice_id': 99,
                }
            ],
            'payment_method_id': 375,
            'name': u'Remesa 0002',
        }
        self.assertEqual(related_values, expected_values)

    @unittest.skip("This test is not working because of the validate_order method of payment.order,\
                that is called in action_open and that we cannot mock with mock.patch.object for \
               some reason. We should find a way to mock it and then this test will work")
    @mock.patch.object(odoo_sync.OdooSync, "sync_model_enabled_amplified")
    @mock.patch.object(odoo_sync.OdooSync, "syncronize_sync")
    # @mock.patch.object(type(self.po_obj), "validate_order")
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
        self.utils_open_invoice_add_to_order(invoice_id, remesa_id)

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
            with mock.patch('addons.account_payment.payment.payment_order.validate_order',
                            return_value=True):
                # with mock.patch.object(type(self.po_obj), "validate_order", return_value=True):
                wiz_pay_o.action_pagar_remesa_threaded(self.cursor.dbname, self.uid, [
                    wiz_pay_id], context=context)

        mock_syncronize_sync.assert_called_once()

    @mock.patch.object(odoo_sync.OdooSync, "search")
    @mock.patch.object(odoo_sync.OdooSync, "read")
    def test_process_payment_lines_with_discrepancies(self, mock_read, mock_search):
        import json
        cases = [
            (100.0, 5.5, 105.5),   # amount positiu, difference positiu
            (100.0, -5.5, 94.5),   # amount positiu, difference negatiu
            (-100.0, 5.5, -94.5),  # amount negatiu, difference positiu
            (-100.0, -5.5, -105.5),  # amount negatiu, difference negatiu
            (-33.57, -0.01, -33.58),
        ]

        for amount, diff, expected in cases:
            mock_search.return_value = [1]
            mock_read.return_value = [{
                'res_id': 100,
                'odoo_id': 200,
                'odoo_last_update_result': json.dumps(
                    {"data": {"metadata": [
                        {"pnt_amount_total_erp_difference": diff, "move_type": "out_invoice"}]
                    }})
            }]

            lines = [{'invoice_id': 200, 'amount': amount}]
            pl_inv_ids = [100]

            self.po_obj._process_payment_lines_with_discrepancies(
                self.cursor, self.uid, pl_inv_ids, lines, is_grouped=False
            )

            self.assertEqual(lines[0]['amount'], expected,
                             "Failed for amount=%s, diff=%s" % (amount, diff))

    @mock.patch.object(odoo_sync.OdooSync, "search")
    @mock.patch.object(odoo_sync.OdooSync, "read")
    def test_process_payment_lines_with_discrepancies_grouped(self, mock_read, mock_search):
        import json
        cases = [
            # amount_initial, diff, move_type, expected_amount
            (-200.0, -2.0, 'out_invoice', -202.0),
            (-200.0, 2.0, 'out_invoice', -198.0),
            (-200.0, -2.0, 'out_refund', -198.0),
            (-200.0, 2.0, 'out_refund', -202.0),
        ]

        for amount, diff, move_type, expected in cases:
            mock_search.return_value = [1]
            mock_read.return_value = [{
                'res_id': 101,
                'odoo_id': 201,
                'odoo_last_update_result': json.dumps({
                    "data": {
                        "metadata": [{
                            "pnt_amount_total_erp_difference": diff,
                            "move_type": move_type
                        }]
                    }
                })
            }]

            lines = [{'invoice_ids': [201, 202], 'amount': amount}]
            pl_inv_ids = [101]

            self.po_obj._process_payment_lines_with_discrepancies(
                self.cursor, self.uid, pl_inv_ids, lines, is_grouped=True
            )

            self.assertEqual(lines[0]['amount'], expected,
                             "Failed for grouped amount={}, diff={}, move_type={}".format(
                                 amount, diff, move_type))

    @mock.patch.object(odoo_sync.OdooSync, "search")
    def test_process_payment_lines_with_discrepancies_no_diffs(self, mock_search):
        mock_search.return_value = []

        lines = [{'invoice_id': 200, 'amount': 100.0}]
        pl_inv_ids = [100]

        self.po_obj._process_payment_lines_with_discrepancies(
            self.cursor, self.uid, pl_inv_ids, lines, is_grouped=False
        )

        self.assertEqual(lines[0]['amount'], 100.0)

    def test_get_total_amount_difference(self):
        # Valid JSON string
        record = {
            'odoo_last_update_result': '{"data": {"metadata": [{"pnt_amount_total_erp_difference": 5.5, "move_type": "out_invoice"}]}}'  # noqa: E501
        }
        res, move_type = self.po_obj._get_total_amount_difference(record)
        self.assertEqual(res, 5.5)
        self.assertEqual(move_type, "out_invoice")

        # Dictionary instead of string
        record2 = {
            'odoo_last_update_result': {"data": {"metadata": [{"pnt_amount_total_erp_difference": 3.0, "move_type": "out_refund"}]}}  # noqa: E501
        }
        res2, move_type2 = self.po_obj._get_total_amount_difference(record2)
        self.assertEqual(res2, 3.0)
        self.assertEqual(move_type2, "out_refund")

        # Invalid / missing keys
        record3 = {
            'odoo_last_update_result': '{"data": {}}'
        }
        res3, move_type3 = self.po_obj._get_total_amount_difference(record3)
        self.assertEqual(res3, 0)
        self.assertIsNone(move_type3)

        # Empty
        res4, move_type4 = self.po_obj._get_total_amount_difference({})
        self.assertEqual(res4, 0)
        self.assertIsNone(move_type4)
