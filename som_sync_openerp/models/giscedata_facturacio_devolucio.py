#  -*- coding: utf-8 -*-
from osv import osv


class GiscedataFacturacioDevolucio(osv.osv):
    _name = 'giscedata.facturacio.devolucio'
    _inherit = 'giscedata.facturacio.devolucio'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'number',
        'total_devolution': 'amount',
        'date': 'date',

    }
    MAPPING_FK = {
        'pay_account_id': 'account.account',
        'pay_journal_id': 'account.journal',
    }
    MAPPING_CONSTANTS = {
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        inv_obj = self.pool.get('account.invoice')
        dev_lin_obj = self.pool.get('giscedata.facturacio.devolucio.linia')

        lines = []

        context_copy = context.copy()
        context_copy['from_fk_sync'] = True
        # we get the lines from 'numfactura' from devolucio lines
        dev_lin_ids = dev_lin_obj.search(cr, uid, [('devolucio_id', '=', id)])
        numfacts = dev_lin_obj.read(cr, uid, dev_lin_ids, ['numfactura', 'import'])
        for numfact in numfacts:
            invoice_ids = inv_obj.search(cr, uid, [('number', '=', numfact['numfactura'])])
            if invoice_ids:
                invoice_id = invoice_ids[0]
                odoo_id, _ = sync_obj.common_sync_model_create_update(
                    cr, uid, 'account.invoice', 'sync', invoice_id, context_copy)
                line = {
                    'invoice_id': odoo_id,
                    'amount': numfact['import'],
                }
                lines.append(line)

        res = {
            'lines': lines,
        }
        return res


GiscedataFacturacioDevolucio()
