
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
        self.conf_obj = self.openerp.pool.get("res.config")
        self.maxDiff = None
        super(TestPaymentOrder, self).setUp()

    def utils_add_splitted_line_to_order(self, order_id, amount=500.0):
        """
        Crea una payment.line sense ml_inv_ref i amb un move_line_id
        el moviment del qual no té cap factura associada (cas fraccionament).
        """
        am_obj = self.openerp.pool.get("account.move")
        aml_obj = self.openerp.pool.get("account.move.line")

        journal_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_journal_syncronizable"
        )[1]
        period_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "period_012026"
        )[1]
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_agrolait"
        )[1]

        move_id = am_obj.create(self.cursor, self.uid, {
            'journal_id': journal_id,
            'period_id': period_id,
            'date': '2026-01-15',
        })
        receivable_account_id = self.openerp.pool.get("account.account").search(
            self.cursor, self.uid, [('type', '=', 'receivable')], limit=1
        )[0]
        move_line_id = aml_obj.create(self.cursor, self.uid, {
            'move_id': move_id,
            'name': 'Fraccionament test',
            'debit': amount,
            'credit': 0.0,
            'account_id': receivable_account_id,
            'partner_id': partner_id,
            'journal_id': journal_id,
            'period_id': period_id,
        })
        self.pl_obj.create(self.cursor, self.uid, {
            'order_id': order_id,
            'move_line_id': move_line_id,
            'partner_id': partner_id,
            'name': 'Fraccionament test',
            'date': '2026-01-15',
            'state': 'normal',
            'communication': 'Fraccionament test',
            'amount_currency': amount,
            'currency': self.openerp.pool.get("res.currency").search(
                self.cursor, self.uid, [('name', '=', 'EUR')], limit=1
            )[0],
        })

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

    def utils_open_invoice_add_to_order_with_ml_inv_ref(self, invoice_id, order_id):
        self.wf_service.trg_validate(
            self.uid, 'account.invoice', invoice_id, 'invoice_open', self.cursor
        )
        invoice = self.ai_obj.browse(self.cursor, self.uid, invoice_id)
        move_line_id = None
        for line in invoice.move_id.line_id:
            if line.account_id.type == 'receivable':
                move_line_id = line.id
                break
        self.pl_obj.create(self.cursor, self.uid, {
            'order_id': order_id,
            'move_line_id': move_line_id,
            'ml_inv_ref': invoice_id,
            'partner_id': invoice.partner_id.id,
            'name': invoice.name or '/',
            'date': invoice.date_invoice,
            'state': 'normal',
            'communication': invoice.name or '/',
            'amount_currency': invoice.amount_total,
            'currency': invoice.currency_id.id,
        })

    def utils_create_invoice_without_payment_order(self):
        """
        Crea una factura sense payment_order_id per poder afegir-la a una
        payment.order sense que s'informe ml_inv_ref automàticament.
        """
        journal_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_journal_sales_syncronizable"
        )[1]
        period_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "period_012026"
        )[1]
        invoice_id = self.ai_obj.create(self.cursor, self.uid, {
            'name': 'Grouped invoice test',
            'type': 'out_invoice',
            'state': 'draft',
            'date_invoice': '2026-01-16',
            'partner_id': self.imd_obj.get_object_reference(
                self.cursor, self.uid, "base", "res_partner_9"
            )[1],
            'address_invoice_id': self.imd_obj.get_object_reference(
                self.cursor, self.uid, "base", "res_partner_address_1"
            )[1],
            'period_id': period_id,
            'account_id': self.imd_obj.get_object_reference(
                self.cursor, self.uid, "account", "a_recv"
            )[1],
            'journal_id': journal_id,
        })
        self.ail_obj.create(self.cursor, self.uid, {
            'invoice_id': invoice_id,
            'name': 'Product grouped',
            'price_unit': 1000.0,
            'quantity': 1,
            'account_id': self.imd_obj.get_object_reference(
                self.cursor, self.uid, "account", "a_sale"
            )[1],
        })
        return invoice_id

    def utils_create_fraccionament_in_order(self, order_id, import_amount=500.0):
        """
        Crea un account.invoice.fraccionament.fraccionaments amb remesa_desti_id
        apuntant a la payment.order donada, i la payment.line corresponent.
        Simula el cas splitted.
        """
        import time
        aiff_obj = self.openerp.pool.get("account.invoice.fraccionament.fraccionaments")
        am_obj = self.openerp.pool.get("account.move")
        aml_obj = self.openerp.pool.get("account.move.line")

        unique_name = 'Fraccionament test {}'.format(time.time())

        journal_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_journal_syncronizable"
        )[1]
        period_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "period_012026"
        )[1]
        partner_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "base", "res_partner_agrolait"
        )[1]
        receivable_account_id = self.openerp.pool.get("account.account").search(
            self.cursor, self.uid, [('type', '=', 'receivable')], limit=1
        )[0]

        move_id = am_obj.create(self.cursor, self.uid, {
            'journal_id': journal_id,
            'period_id': period_id,
            'date': '2026-01-15',
        })
        move_line_id = aml_obj.create(self.cursor, self.uid, {
            'move_id': move_id,
            'name': unique_name,
            'debit': import_amount,
            'credit': 0.0,
            'account_id': receivable_account_id,
            'partner_id': partner_id,
            'journal_id': journal_id,
            'period_id': period_id,
        })
        self.pl_obj.create(self.cursor, self.uid, {
            'order_id': order_id,
            'move_line_id': move_line_id,
            'partner_id': partner_id,
            'name': unique_name,
            'date': '2026-01-15',
            'state': 'normal',
            'communication': unique_name,
            'amount_currency': import_amount,
            'currency': self.openerp.pool.get("res.currency").search(
                self.cursor, self.uid, [('name', '=', 'EUR')], limit=1
            )[0],
        })
        fracc_id = aiff_obj.create(self.cursor, self.uid, {
            'move_line_id': move_line_id,
            'import': import_amount,
            'remesa_desti_id': order_id,
            'state': 'remesat',
            'data_venciment': '2026-01-15',
            'company_id': self.imd_obj.get_object_reference(
                self.cursor, self.uid, "base", "main_company"
            )[1],
        })
        return fracc_id

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__get_journal_odoo_id_uses_payment_mode_bank(self, mock_get_odoo_id_by_erp_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        journal_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "account_journal_syncronizable"
        )[1]
        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        mock_get_odoo_id_by_erp_id.return_value = 13

        journal_odoo_id = self.po_obj._get_journal_odoo_id(
            self.cursor, self.uid, payment_order
        )

        self.assertEqual(journal_odoo_id, 13)
        mock_get_odoo_id_by_erp_id.assert_called_once_with(
            self.cursor, self.uid, 'account.journal', journal_id)

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__get_journal_odoo_id_returns_false_when_payment_mode_has_no_bank(
            self, mock_get_odoo_id_by_erp_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        with mock.patch.object(payment_order, 'mode', False, create=True):
            journal_odoo_id = self.po_obj._get_journal_odoo_id(
                self.cursor, self.uid, payment_order
            )

        self.assertFalse(journal_odoo_id)
        mock_get_odoo_id_by_erp_id.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__get_journal_odoo_id_returns_false_when_journal_has_no_odoo_mapping(
            self, mock_get_odoo_id_by_erp_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        mock_get_odoo_id_by_erp_id.return_value = False

        journal_odoo_id = self.po_obj._get_journal_odoo_id(
            self.cursor, self.uid, payment_order
        )

        self.assertFalse(journal_odoo_id)
        mock_get_odoo_id_by_erp_id.assert_called_once()

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__get_journal_odoo_id_returns_false_when_no_journal_matches_bank(
            self, mock_get_odoo_id_by_erp_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)

        with mock.patch.object(self.aj_obj, 'search', return_value=[]):
            journal_odoo_id = self.po_obj._get_journal_odoo_id(
                self.cursor, self.uid, payment_order
            )

        self.assertFalse(journal_odoo_id)
        mock_get_odoo_id_by_erp_id.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    def test__get_journal_odoo_id_returns_false_when_multiple_journals_match_bank(
            self, mock_get_odoo_id_by_erp_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        self.aj_obj.create(self.cursor, self.uid, {
            'name': 'Duplicate bank journal',
            'code': 'DupBank',
            'type': 'general',
            'som_sync_bank_id': payment_order.mode.bank_id.id,
            'view_id': self.imd_obj.get_object_reference(
                self.cursor, self.uid, 'account', 'account_journal_view'
            )[1],
            'sequence_id': self.imd_obj.get_object_reference(
                self.cursor, self.uid, 'account', 'sequence_journal'
            )[1],
        })

        journal_odoo_id = self.po_obj._get_journal_odoo_id(
            self.cursor, self.uid, payment_order
        )

        self.assertFalse(journal_odoo_id)
        mock_get_odoo_id_by_erp_id.assert_not_called()

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
        odoo_journal_id = 13
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
            'payment_method_line_id': 373,
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
        odoo_journal_id = 13
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
            'payment_method_line_id': 375,
            'name': u'Remesa 0002',
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id_from_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_splitted_returns_payment_ids_and_amount(
            self, mock_sync_create_update, mock_get_odoo_id, mock_get_odoo_id_by_erp_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        odoo_payment_id_1 = 101
        odoo_payment_id_2 = 102
        payment_method_line_id = eval(
            self.conf_obj.get(
                self.cursor, self.uid, 'odoo_customer_fraccionaments_payment_method', 0
            ))

        mock_sync_create_update.return_value = (999, 1)
        mock_get_odoo_id.side_effect = [odoo_payment_id_1, odoo_payment_id_2]
        mock_get_odoo_id_by_erp_id.return_value = 13

        self.utils_create_fraccionament_in_order(remesa_id, import_amount=300.0)
        self.utils_create_fraccionament_in_order(remesa_id, import_amount=200.0)

        related_values = self.po_obj.get_related_values(
            self.cursor, self.uid, remesa_id
        )

        expected_values = {
            'destination_journal_id': 13,
            'payment_method_line_id': payment_method_line_id,
            'payment_ids': [odoo_payment_id_1, odoo_payment_id_2],
            'amount': 500.0,
            'name': u'Remesa 0001',
        }
        self.assertEqual(related_values, expected_values)

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id")
    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id_from_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_related_values_splitted_amount_is_rounded(
            self, mock_sync_create_update, mock_get_odoo_id, mock_get_odoo_id_by_erp_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        mock_sync_create_update.return_value = (999, 1)
        mock_get_odoo_id.return_value = 999
        mock_get_odoo_id_by_erp_id.return_value = 13

        self.utils_create_fraccionament_in_order(remesa_id, import_amount=100.005)
        self.utils_create_fraccionament_in_order(remesa_id, import_amount=100.005)

        related_values = self.po_obj.get_related_values(
            self.cursor, self.uid, remesa_id
        )

        self.assertEqual(related_values['amount'], round(200.01, 2))

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

            self.ai_obj.process_lines_with_discrepancies(
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

            self.ai_obj.process_lines_with_discrepancies(
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

        self.ai_obj.process_lines_with_discrepancies(
            self.cursor, self.uid, pl_inv_ids, lines, is_grouped=False
        )

        self.assertEqual(lines[0]['amount'], 100.0)

    @mock.patch('som_sync_openerp.models.odoo_sync.OdooSync.update_odoo_id')
    @mock.patch('som_sync_openerp.models.payment_order.requests.get')
    @mock.patch.object(odoo_sync.OdooSync, "_get_conn_params")
    def test_update_pending_state_marks_record_as_synced(
        self, mock_get_conn_params, mock_requests_get, mock_update_odoo_id
    ):
        mock_get_conn_params.return_value = (
            'http://example.com/api/',
            'test-api-key',
        )
        mock_response = mock.Mock()
        mock_response.status_code = 200
        payment_order_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'remesa_0001'
        )[1]
        mock_response.json.return_value = {
            'success': True,
            'message': 'Record found successfully',
            'data': {
                'odoo_id': 92,
                'erp_id': payment_order_id,
                'status': 'done',
                'processed': False,
                'confirmed': False,
            },
        }
        mock_requests_get.return_value = mock_response
        mock_update_odoo_id.return_value = True

        result = self.po_obj.update_pending_state_sync(
            self.cursor, self.uid, payment_order_id, {}
        )

        self.assertTrue(result)
        mock_requests_get.assert_called_once_with(
            'http://example.com/api/payment_orders/{}/status'.format(payment_order_id),
            headers={
                'X-API-Key': 'test-api-key',
                'Accept': 'application/json',
            },
        )
        mock_update_odoo_id.assert_called_once()
        _, kwargs = mock_update_odoo_id.call_args
        self.assertEqual(kwargs['context'], {
            'sync_state': 'synced',
            'update_last_sync': True,
        })

    @mock.patch('som_sync_openerp.models.odoo_sync.OdooSync.update_odoo_id')
    @mock.patch('som_sync_openerp.models.payment_order.requests.get')
    @mock.patch.object(odoo_sync.OdooSync, "_get_conn_params")
    def test_update_pending_state_marks_record_as_error(
        self, mock_get_conn_params, mock_requests_get, mock_update_odoo_id
    ):
        mock_get_conn_params.return_value = (
            'http://example.com/api/',
            'test-api-key',
        )
        mock_response = mock.Mock()
        mock_response.status_code = 200
        payment_order_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'remesa_0001'
        )[1]
        mock_response.json.return_value = {
            'success': True,
            'message': 'Record found successfully',
            'data': {
                'odoo_id': 92,
                'erp_id': payment_order_id,
                'status': 'error',
                'processed': False,
                'confirmed': False,
            },
        }
        mock_requests_get.return_value = mock_response
        mock_update_odoo_id.return_value = True

        result = self.po_obj.update_pending_state_sync(
            self.cursor, self.uid, payment_order_id, {}
        )

        self.assertTrue(result)
        mock_requests_get.assert_called_once_with(
            'http://example.com/api/payment_orders/{}/status'.format(payment_order_id),
            headers={
                'X-API-Key': 'test-api-key',
                'Accept': 'application/json',
            },
        )
        mock_update_odoo_id.assert_called_once()
        _, kwargs = mock_update_odoo_id.call_args
        self.assertEqual(kwargs['context'], {
            'sync_state': 'error',
            'update_last_sync': True,
            'odoo_last_update_result': mock_response,
        })

    def test_get_total_amount_difference(self):
        # Valid JSON string
        record = {
            'odoo_last_update_result': '{"data": {"metadata": [{"pnt_amount_total_erp_difference": 5.5, "move_type": "out_invoice"}]}}'  # noqa: E501
        }
        res, move_type = self.ai_obj._get_total_amount_difference(record)
        self.assertEqual(res, 5.5)
        self.assertEqual(move_type, "out_invoice")

        # Dictionary instead of string
        record2 = {
            'odoo_last_update_result': {"data": {"metadata": [{"pnt_amount_total_erp_difference": 3.0, "move_type": "out_refund"}]}}  # noqa: E501
        }
        res2, move_type2 = self.ai_obj._get_total_amount_difference(record2)
        self.assertEqual(res2, 3.0)
        self.assertEqual(move_type2, "out_refund")

        # Invalid / missing keys
        record3 = {
            'odoo_last_update_result': '{"data": {}}'
        }
        res3, move_type3 = self.ai_obj._get_total_amount_difference(record3)
        self.assertEqual(res3, 0)
        self.assertIsNone(move_type3)

        # Empty
        res4, move_type4 = self.ai_obj._get_total_amount_difference({})
        self.assertEqual(res4, 0)
        self.assertIsNone(move_type4)

    def test__is_order_splitted_invoices_returns_true_when_has_splitted_lines(self):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_add_splitted_line_to_order(remesa_id)

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        result = self.po_obj._is_order_splitted_invoices(self.cursor, self.uid, payment_order)

        self.assertTrue(result)

    def test__is_order_splitted_invoices_returns_false_when_has_normal_invoice_lines(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0004"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_open_invoice_add_to_order(invoice_id, remesa_id)

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        result = self.po_obj._is_order_splitted_invoices(self.cursor, self.uid, payment_order)

        self.assertFalse(result)

    def test__is_order_splitted_invoices_returns_false_when_order_has_no_lines(self):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        result = self.po_obj._is_order_splitted_invoices(self.cursor, self.uid, payment_order)

        self.assertFalse(result)

    # _is_order_grouped_invoices
    def test__is_order_grouped_invoices_returns_true_when_line_has_no_ml_inv_ref_and_move_has_invoices(self):  # noqa: E501
        mock_invoice = mock.Mock()
        mock_aml = mock.Mock()
        mock_aml.invoice = mock_invoice
        mock_move = mock.Mock()
        mock_move.line_id = [mock_aml]
        mock_move_line = mock.Mock()
        mock_move_line.move_id = mock_move
        mock_line = mock.Mock()
        mock_line.ml_inv_ref = False
        mock_line.move_line_id = mock_move_line
        mock_payment_order = mock.Mock()
        mock_payment_order.line_ids = [mock_line]

        result = self.po_obj._is_order_grouped_invoices(
            self.cursor, self.uid, mock_payment_order
        )

        self.assertTrue(result)

    def test__is_order_grouped_invoices_returns_false_when_order_has_no_lines(self):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        result = self.po_obj._is_order_grouped_invoices(self.cursor, self.uid, payment_order)

        self.assertFalse(result)

    def test__is_order_grouped_invoices_returns_false_when_move_has_no_invoices(self):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_add_splitted_line_to_order(remesa_id)

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        result = self.po_obj._is_order_grouped_invoices(self.cursor, self.uid, payment_order)

        self.assertFalse(result)

    # _is_order_refund
    def test__is_order_refund_returns_true_when_line_has_negative_out_invoice(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0003"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_open_invoice_add_to_order_with_ml_inv_ref(invoice_id, remesa_id)

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        result = self.po_obj._is_order_refund(self.cursor, self.uid, payment_order)

        self.assertTrue(result)

    def test__is_order_refund_returns_false_when_line_has_positive_invoice(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0004"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_open_invoice_add_to_order_with_ml_inv_ref(invoice_id, remesa_id)

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        result = self.po_obj._is_order_refund(self.cursor, self.uid, payment_order)

        self.assertFalse(result)

        result = self.po_obj._is_order_refund(self.cursor, self.uid, payment_order)

        self.assertFalse(result)

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id_from_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_order_payment_lines_from_splitted_invoices_returns_payment_ids_and_amount(
            self, mock_sync_create_update, mock_get_odoo_id):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        odoo_payment_id_1 = 201
        odoo_payment_id_2 = 202
        mock_sync_create_update.return_value = (999, 1)
        mock_get_odoo_id.side_effect = [odoo_payment_id_1, odoo_payment_id_2]

        self.utils_create_fraccionament_in_order(remesa_id, import_amount=400.0)
        self.utils_create_fraccionament_in_order(remesa_id, import_amount=100.0)

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        payment_ids, amount = self.po_obj._get_order_payment_lines_from_splitted_invoices(
            self.cursor, self.uid, payment_order
        )

        self.assertEqual(payment_ids, [odoo_payment_id_1, odoo_payment_id_2])
        self.assertEqual(amount, 500.0)

    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_order_payment_lines_from_splitted_invoices_returns_empty_when_no_fraccionaments(
            self, mock_sync_create_update):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        payment_ids, amount = self.po_obj._get_order_payment_lines_from_splitted_invoices(
            self.cursor, self.uid, payment_order
        )

        self.assertEqual(payment_ids, [])
        self.assertEqual(amount, 0.0)
        mock_sync_create_update.assert_not_called()

    @mock.patch.object(odoo_sync.OdooSync, "get_odoo_id_by_erp_id_from_odoo")
    @mock.patch.object(odoo_sync.OdooSync, "common_sync_model_create_update")
    def test__get_order_payment_lines_from_splitted_invoices_syncs_fraccionament_parent(
            self, mock_sync_create_update, mock_get_odoo_id):
        """
        Verifica que es syncronitza el fraccionament pare (account.invoice.fraccionament)
        i no la línia individual. El pare s'obté via invoice_fraccionament_id.
        Si la línia no té pare assignat, no es fa cap sync.
        """
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        mock_sync_create_update.return_value = (999, 1)
        mock_get_odoo_id.return_value = None

        # línia sense invoice_fraccionament_id: no ha de syncronitzar cap pare
        self.utils_create_fraccionament_in_order(remesa_id, import_amount=300.0)

        payment_order = self.po_obj.browse(self.cursor, self.uid, remesa_id)
        payment_ids, amount = self.po_obj._get_order_payment_lines_from_splitted_invoices(
            self.cursor, self.uid, payment_order
        )

        mock_sync_create_update.assert_not_called()
        self.assertEqual(payment_ids, [False])
        self.assertEqual(amount, 0.0)

    def test__get_mapping_model_post_returns_payment_order_payments_when_splitted(self):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_create_fraccionament_in_order(remesa_id, import_amount=300.0)

        result = self.po_obj.get_mapping_model_post(self.cursor, self.uid, remesa_id)

        self.assertEqual(result, 'payment_orders/payments')

    def test__get_mapping_model_post_returns_payment_orders_when_normal(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0004"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_open_invoice_add_to_order(invoice_id, remesa_id, factor=-1)

        result = self.po_obj.get_mapping_model_post(self.cursor, self.uid, remesa_id)

        self.assertEqual(result, 'payment_orders')

    @mock.patch('som_sync_openerp.models.payment_order.PaymentOrder._is_order_refund', return_value=False)  # noqa: E501
    @mock.patch('som_sync_openerp.models.payment_order.PaymentOrder._is_order_splitted_invoices', return_value=False)  # noqa: E501
    @mock.patch('som_sync_openerp.models.payment_order.PaymentOrder._is_order_grouped_invoices', return_value=True)  # noqa: E501
    def test__get_mapping_model_post_returns_payment_order_batches_when_grouped(
            self, mock_grouped, mock_splitted, mock_refund):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        result = self.po_obj.get_mapping_model_post(self.cursor, self.uid, remesa_id)
        self.assertEqual(result, 'payment_orders/batches')

    def test__get_mapping_model_post_returns_payment_order_refunds_when_refund(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0003"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_open_invoice_add_to_order_with_ml_inv_ref(invoice_id, remesa_id)

        result = self.po_obj.get_mapping_model_post(self.cursor, self.uid, remesa_id)

        self.assertEqual(result, 'payment_order_refunds')

    def test__get_sync_state_on_creation_returns_pending_when_normal(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0004"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_open_invoice_add_to_order(invoice_id, remesa_id, factor=-1)

        result = self.po_obj.get_sync_state_on_creation(self.cursor, self.uid, remesa_id)

        self.assertEqual(result, 'pending')

    def test__get_sync_state_on_creation_returns_synced_when_splitted(self):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_create_fraccionament_in_order(remesa_id, import_amount=300.0)

        result = self.po_obj.get_sync_state_on_creation(self.cursor, self.uid, remesa_id)

        self.assertEqual(result, 'synced')

    def test__get_sync_state_on_creation_returns_synced_when_grouped(self):
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        with mock.patch.object(
            type(self.po_obj), '_is_order_grouped_invoices', return_value=True
        ):
            result = self.po_obj.get_sync_state_on_creation(self.cursor, self.uid, remesa_id)

        self.assertEqual(result, 'synced')

    def test__get_sync_state_on_creation_returns_synced_when_refund(self):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "invoice_0003"
        )[1]
        remesa_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, "som_sync_openerp", "remesa_0001"
        )[1]
        self.utils_open_invoice_add_to_order_with_ml_inv_ref(invoice_id, remesa_id)

        result = self.po_obj.get_sync_state_on_creation(self.cursor, self.uid, remesa_id)

        self.assertEqual(result, 'synced')
