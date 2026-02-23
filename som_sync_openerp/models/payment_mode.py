#  -*- coding: utf-8 -*-
from osv import osv, fields


class PaymentMode(osv.osv):
    _name = "payment.mode"
    _inherit = "payment.mode"

    _columns = {
        'som_sync_odoo': fields.boolean(
            'Sync with Odoo payment orders',
            help='If checked, the payment orders with this \
                payment mode will be synchronize Moves with Odoo.'),
    }

    _defaults = {
        'som_sync_odoo': lambda *a, **k: False,
    }


PaymentMode()
