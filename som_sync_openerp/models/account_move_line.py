#  -*- coding: utf-8 -*-
from osv import osv


class AccountMoveLine(osv.osv):
    _name = 'account.move.line'
    _inherit = 'account.move.line'

    MAPPING_FIELDS_TO_SYNC = {
        'account_id': 'account_id',
        'partner_id': 'partner_id',
        'name': 'name',
        'ref': 'ref',
        'debit': 'debit',
        'credit': 'credit',
    }
    MAPPING_FK = {
        'account_id': 'account.account',
        'partner_id': 'res.partner',
    }
    MAPPING_CONSTANTS = {
    }

    def hook_last_modifications(self, cr, uid, data, context=None):
        if context is None:
            context = {}
        data['name'] = data.get('ref', False) or data.get('name', '')
        data.pop('ref', False)
        return data


AccountMoveLine()
