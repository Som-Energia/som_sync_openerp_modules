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
        fact_obj = self.pool.get('giscedata.facturacio.factura')

        lines = []

        # we get the lines
        fact_ids = fact_obj.search(cr, uid, [('devolucio_id', '=', id)])
        context_copy = context.copy()
        context_copy['from_fk_sync'] = True
        for fact in fact_obj.browse(cr, uid, fact_ids, context=context):
            erp_invoice_id = fact.invoice_id.id
            odoo_id, _ = sync_obj.common_sync_model_create_update(
                cr, uid, 'account.invoice', 'sync', erp_invoice_id, context_copy)
            line = {
                'invoice_id': odoo_id,
                'amount': abs(fact.amount_total),
            }
            lines.append(line)

        res = {
            'lines': lines,
        }
        return res


GiscedataFacturacioDevolucio()
