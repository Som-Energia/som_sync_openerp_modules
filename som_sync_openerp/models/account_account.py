#  -*- coding: utf-8 -*-
from osv import osv, fields
from service.security import Sudo


class AccountAccount(osv.osv):
    _name = 'account.account'
    _inherit = 'account.account'

    MAPPING_FIELDS_TO_SYNC = {
        'name': 'name',
        'code': 'code',
        'odoo_account_code': 'odoo_account_code',
        'id': 'pnt_erp_id',
    }
    MAPPING_FK = {
    }
    MAPPING_CONSTANTS = {
    }

    _columns = {
        'odoo_account_code': fields.char(
            'Odoo account code', size=9, select=1,
        ),
    }

    _sql_constraints = [
        (
            'odoo_account_code_format',
            "CHECK (odoo_account_code IS NULL OR odoo_account_code ~ '^[0-9]{9}$')",
            'The Odoo account code must contain exactly 9 digits.',
        ),
    ]

    def get_endpoint_suffix(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        account = self.browse(cr, uid, id, context=context)
        return account.odoo_account_code or account.code or False

    def hook_last_modifications(self, cr, uid, data, context=None):
        odoo_account_code = data.pop('odoo_account_code', False)
        if odoo_account_code:
            data['code'] = odoo_account_code
        return data

    def check_special_restrictions(self, cr, uid, id, context=None):
        account = self.browse(cr, uid, id, context=context)
        return len(account.code or '') != 12 or bool(account.odoo_account_code)

    def create(self, cr, uid, vals, context=None):
        if context is None:
            context = {}
        ids = super(AccountAccount, self).create(cr, uid, vals, context=context)

        with Sudo(uid=1, gid=0):
            sync_obj = self.pool.get('odoo.sync')
            sync_obj.common_sync_model_create_update(
                cr, uid, self._name, 'create', ids, context=context
            )

        return ids


AccountAccount()
