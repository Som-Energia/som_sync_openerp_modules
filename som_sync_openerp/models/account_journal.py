#  -*- coding: utf-8 -*-
from osv import osv, fields


class AccountJournal(osv.osv):
    _name = 'account.journal'
    _inherit = 'account.journal'

    _columns = {
        'som_sync_odoo_account_moves': fields.boolean(
            'Sync with Odoo Account Moves',
            help='If checked, this journal will be synchronize Moves with Odoo.'),
        'som_sync_odoo_invoices': fields.boolean(
            'Sync with Odoo Invoices',
            help='If checked, this journal will be synchronize Invoices with Odoo.'),
    }

    _defaults = {
        'som_sync_odoo_account_moves': lambda *a, **k: False,
        'som_sync_odoo_invoices': lambda *a, **k: False,
    }


AccountJournal()
