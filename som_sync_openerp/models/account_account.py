#  -*- coding: utf-8 -*-
from osv import osv


class AccountAccount(osv.osv):
    _name = 'account.account'
    _inherit = 'account.account'

    MAPPING_FIELDS_TO_SYNC = {
        'name': 'name',
        'code': 'code',
        'id': 'pnt_erp_id',
    }
    MAPPING_FK = {
    }
    MAPPING_CONSTANTS = {
    }

    def get_endpoint_suffix(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account = self.browse(cr, uid, id, context=context)
        if account.code:
            res = '{}'.format(account.code)
            return res
        else:
            return False

    def create(self, cr, uid, vals, context=None):
        if context is None:
            context = {}
        ids = super(AccountAccount, self).create(cr, uid, vals, context=context)

        sync_obj = self.pool.get('odoo.sync')
        sync_obj.common_sync_model_create_update(
            cr, uid, self._name, ids, 'create', context=context
        )

        return ids


AccountAccount()
