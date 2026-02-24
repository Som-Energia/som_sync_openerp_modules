#  -*- coding: utf-8 -*-
from osv import osv


class PaymentLine(osv.osv):
    _name = 'payment.line'
    _inherit = 'payment.line'

    MAPPING_FIELDS_TO_SYNC = {
        'ml_inv_ref': 'invoice_id',
    }
    MAPPING_FK = {
        'ml_inv_ref': 'account.invoice',
    }
    MAPPING_CONSTANTS = {
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        payment_line = self.browse(cr, uid, id, context=context)
        res = {}
        factor = -1 if payment_line.order_id.type == 'receivable' else 1
        res = {
            'amount': payment_line.amount * factor,
        }
        return res


PaymentLine()
