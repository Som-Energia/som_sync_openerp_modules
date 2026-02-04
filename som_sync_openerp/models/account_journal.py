#  -*- coding: utf-8 -*-
from osv import osv, fields


class AccountJournal(osv.osv):
    _name = 'account.journal'
    _inherit = 'account.journal'

    _columns = {
        'som_sync_odoo': fields.boolean(
            'Sync with Odoo',
            help='If checked, this journal will be synchronized with Odoo.'),
    }


AccountJournal()
