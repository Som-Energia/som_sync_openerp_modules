#  -*- coding: utf-8 -*-
from osv import osv


class AccountMove(osv.osv):
    _name = 'account.move'
    _inherit = 'account.move'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'name',
        'journal_id': 'journal_id',
        'ref': 'ref',
        'date': 'date',
    }
    MAPPING_FK = {
        'journal_id': 'account.journal',
    }
    MAPPING_CONSTANTS = {
    }

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account_move = self.browse(cr, uid, id, context=context)
        res = []
        for line in account_move.line_id:
            sync_obj = self.pool.get('odoo.sync')
            aml_vals = sync_obj.get_model_vals_to_sync(
                cr, uid, 'account.move.line', line.id, context=context)
            if aml_vals['debit'] == 0:
                # remove the item from the dictionary
                aml_vals.pop('debit')
            if aml_vals['credit'] == 0:
                # remove the item from the dictionary
                aml_vals.pop('credit')
            res.append(aml_vals)
        return {'lines': res}

    def _journal_is_syncrozable(self, cr, uid, _id, context=None):
        move = self.browse(cr, uid, _id, context=context)
        return move.journal_id and move.journal_id.som_sync_odoo_account_moves

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        res = super(AccountMove, self).write(cr, uid, ids, vals, context=context)

        for _id in ids:
            if self._journal_is_syncrozable(cr, uid, _id, context=context) and \
                'state' in vals and \
                    vals['state'] == 'posted':
                sync_obj = self.pool.get('odoo.sync')
                sync_obj.common_sync_model_create_update(
                    cr, uid, self._name, _id, 'create', context=context
                )

        return res


AccountMove()
