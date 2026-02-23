#  -*- coding: utf-8 -*-
from osv import osv


class PaymentOrder(osv.osv):
    _name = 'payment.order'
    _inherit = 'payment.order'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'name',
        'date_created': 'date',  # TODO: check if date_created is the one's
        'date_planned': 'sdd_required_collection_date',
        'total': 'amount',
    }

    MAPPING_FK = {
    }

    MAPPING_CONSTANTS = {
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        payment_order = self.browse(cr, uid, id, context=context)
        lines = []
        sync_obj = self.pool.get('odoo.sync')
        for line in payment_order.line_ids:
            payment_line_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'payment.line', line.id, context=context)
            lines.append(payment_line_vals)
        res = {
            'batch_type': 'outbound' if payment_order.type == 'payable' else 'inbound',
            'journal_destiny': (
                payment_order.mode.journal.id if payment_order.mode.journal else False),
            'lines': lines,
        }
        return res


PaymentOrder()
