#  -*- coding: utf-8 -*-
from osv import osv


class PaymentLine(osv.osv):
    _name = 'payment.line'
    _inherit = 'payment.line'

    MAPPING_FIELDS_TO_SYNC = {
        'amount': 'amount',
        'ml_inv_ref': 'invoice_id',
    }
    MAPPING_FK = {
        'ml_inv_ref': 'account.invoice',
    }
    MAPPING_CONSTANTS = {
    }


PaymentLine()
