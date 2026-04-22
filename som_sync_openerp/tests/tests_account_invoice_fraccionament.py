# -*- coding: utf-8 -*-
from __future__ import absolute_import

from destral import testing
import mock

from ..models import odoo_sync


class TestAccountInvoiceFraccionament(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.imd_obj = self.openerp.pool.get('ir.model.data')
        self.frac_obj = self.openerp.pool.get('account.invoice.fraccionament')
        self.frac_line_obj = self.openerp.pool.get('account.invoice.fraccionament.fraccionaments')
        self.inv_obj = self.openerp.pool.get('account.invoice')
        self.sync_obj = self.openerp.pool.get('odoo.sync')
        self.maxDiff = None
        super(TestAccountInvoiceFraccionament, self).setUp()

    def _create_fraccionament(self, invoice_id):
        """Helper to create a fraccionament with two lines for the given invoice."""
        tipus_ids = self.openerp.pool.get(
            'account.invoice.fraccionament.payment.mode'
        ).search(self.cursor, self.uid, [], limit=1)
        self.assertTrue(tipus_ids, "No payment mode found. Check demo data.")
        tipus_id = tipus_ids[0]

        periodicitat_ids = self.openerp.pool.get(
            'account.invoice.fraccionament.periodicitat'
        ).search(self.cursor, self.uid, [], limit=1)
        self.assertTrue(periodicitat_ids, "No periodicitat found. Check demo data.")
        periodicitat_id = periodicitat_ids[0]

        company_id = self.openerp.pool.get('res.company').search(
            self.cursor, self.uid, [], limit=1)[0]

        frac_id = self.frac_obj.create(self.cursor, self.uid, {
            'invoice_id': invoice_id,
            'codi': 'TEST_FRAC_001',
            'terminis': 2,
            'import_a_fraccionar': 200.0,
            'data_inici_terminis': '2025-01-01',
            'periodicitat': periodicitat_id,
            'tipus': tipus_id,
            'company_id': company_id,
        })

        self.frac_line_obj.create(self.cursor, self.uid, {
            'invoice_fraccionament_id': frac_id,
            'import': 100.0,
            'data_venciment': '2025-01-31',
            'tipus': tipus_id,
            'company_id': company_id,
        })
        self.frac_line_obj.create(self.cursor, self.uid, {
            'invoice_fraccionament_id': frac_id,
            'import': 100.0,
            'data_venciment': '2025-02-28',
            'tipus': tipus_id,
            'company_id': company_id,
        })
        return frac_id

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    @mock.patch.object(odoo_sync.OdooSync, 'get_odoo_id_by_erp_id')
    def test__get_related_values(
        self, mock_get_odoo_id, mock_common_sync
    ):
        invoice_id = self.imd_obj.get_object_reference(
            self.cursor, self.uid, 'som_sync_openerp', 'invoice_0001'
        )[1]
        odoo_invoice_id = 9001
        odoo_payment_method_id = 411

        mock_common_sync.return_value = (odoo_invoice_id, invoice_id)
        mock_get_odoo_id.return_value = odoo_payment_method_id

        frac_id = self._create_fraccionament(invoice_id)
        frac_line_obj = self.openerp.pool.get('account.invoice.fraccionament.fraccionaments')
        frac_line_ids = frac_line_obj.search(
            self.cursor, self.uid, [('invoice_fraccionament_id', '=', frac_id)])
        frac_lines = frac_line_obj.read(
            self.cursor, self.uid, frac_line_ids, ['import', 'data_venciment'])

        related_values = self.frac_obj.get_related_values(
            self.cursor, self.uid, frac_id, context={}
        )

        self.assertEqual(related_values['invoice_id'], odoo_invoice_id)
        self.assertEqual(related_values['payment_method_id'], odoo_payment_method_id)
        self.assertEqual(related_values['amount_total'], 200.0)
        self.assertEqual(len(related_values['lines']), 2)

        expected_lines = [
            {
                'pnt_erp_id': frac_lines[0]['id'],
                'amount': frac_lines[0]['import'],
                'payment_date': str(frac_lines[0]['data_venciment']),
            },
            {
                'pnt_erp_id': frac_lines[1]['id'],
                'amount': frac_lines[1]['import'],
                'payment_date': str(frac_lines[1]['data_venciment']),
            },
        ]
        self.assertEqual(
            sorted(related_values['lines'], key=lambda x: x['pnt_erp_id']),
            sorted(expected_lines, key=lambda x: x['pnt_erp_id']),
        )

        # Verify invoice sync was triggered with from_fk_sync context
        mock_common_sync.assert_called_once_with(
            self.cursor, self.uid, 'account.invoice', 'sync', invoice_id,
            mock.ANY
        )
        ctx_used = mock_common_sync.call_args[0][5]
        self.assertTrue(ctx_used.get('from_fk_sync'))

    def test__get_mapping_model_post(self):
        self.assertEqual(
            self.frac_obj.get_mapping_model_post(
                self.cursor, self.uid, erp_id=1
            ),
            'invoices/payments'
        )
