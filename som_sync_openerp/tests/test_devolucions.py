# -*- coding: utf-8 -*-
from __future__ import absolute_import

from destral import testing
import mock

from addons.devolucions_base.tests.test_devolucions import (
    TestsDevolucions as BaseTestsDevolucions,
)
from ..models import odoo_sync


class TestDevolucions(testing.OOTestCaseWithCursor):

    def setUp(self):
        self.dev_obj = self.openerp.pool.get('giscedata.facturacio.devolucio')
        self.dev_lin_obj = self.openerp.pool.get('giscedata.facturacio.devolucio.linia')
        self.inv_obj = self.openerp.pool.get('account.invoice')
        super(TestDevolucions, self).setUp()

    def _crear_devolucion_factura(self):
        # Python 2: calling an unbound method from another class requires
        # an instance of that exact class. We call the underlying function
        # object to reuse the helper with this test class instance.
        helper = getattr(
            BaseTestsDevolucions.crear_devolucion_factura,
            'im_func',
            BaseTestsDevolucions.crear_devolucion_factura
        )
        return helper(self, self.cursor, self.uid)

    @mock.patch.object(odoo_sync.OdooSync, 'common_sync_model_create_update')
    def test__get_related_values(self, mock_common_sync_model_create_update):
        vals = self._crear_devolucion_factura()
        devolucio_id = vals['devolucio_id']

        # crear_devolucion_factura may trigger sync calls as part of the base
        # module workflow setup. We only want to count calls from
        # get_related_values under test.
        mock_common_sync_model_create_update.reset_mock()

        odoo_by_invoice_id = {
            vals['invoice_1_id']: 9001,
            vals['invoice_2_id']: 9002,
        }

        def _mock_sync(cr, uid, model, action, erp_invoice_id, context=None):
            self.assertEqual(model, 'account.invoice')
            self.assertEqual(action, 'sync')
            self.assertTrue(context.get('from_fk_sync'))
            return odoo_by_invoice_id[erp_invoice_id], erp_invoice_id

        mock_common_sync_model_create_update.side_effect = _mock_sync

        related_values = self.dev_obj.get_related_values(
            self.cursor, self.uid, devolucio_id, context={}
        )

        dev_lin_ids = self.dev_lin_obj.search(
            self.cursor, self.uid, [('devolucio_id', '=', devolucio_id)]
        )
        numfacts = self.dev_lin_obj.read(
            self.cursor, self.uid, dev_lin_ids, ['numfactura', 'import']
        )

        expected_lines = []
        for numfact in numfacts:
            invoice_ids = self.inv_obj.search(
                self.cursor, self.uid, [('number', '=', numfact['numfactura'])]
            )
            if not invoice_ids:
                continue
            invoice_id = invoice_ids[0]
            expected_lines.append({
                'invoice_id': odoo_by_invoice_id[invoice_id],
                'amount': numfact['import'],
            })

        self.assertEqual(
            sorted(related_values['lines'], key=lambda x: x['invoice_id']),
            sorted(expected_lines, key=lambda x: x['invoice_id'])
        )
        self.assertEqual(mock_common_sync_model_create_update.call_count, len(expected_lines))
