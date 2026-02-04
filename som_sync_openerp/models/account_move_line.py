#  -*- coding: utf-8 -*-
from osv import osv


class AccountMoveLine(osv.osv):
    _name = 'account.move.line'
    _inherit = 'account.move.line'

    MAPPING_FIELDS_TO_SYNC = {
        'account_id': 'account_id',
        'partner_id': 'partner_id',
        'name': 'name',
        'debit': 'debit',
        'credit': 'credit',
    }
    MAPPING_FK = {
        'account_id': 'account.account',
        'partner_id': 'res.partner',
    }
    MAPPING_CONSTANTS = {
    }


AccountMoveLine()
