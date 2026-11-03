#  -*- coding: utf-8 -*-
import re

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

    def _check_odoo_account_code(self, cr, uid, ids, context=None):
        for account in self.browse(cr, uid, ids, context=context):
            if len(account.code or '') == 12 and not account.odoo_account_code:
                return False
        return True

    _constraints = [
        (
            _check_odoo_account_code,
            'Accounts with a 12-digit code require an Odoo account code.',
            ['code', 'odoo_account_code'],
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
        return self.check_special_restrictions_with_values(
            cr, uid, id, {}, context=context
        )

    def check_special_restrictions_with_values(
            self, cr, uid, id, vals, context=None):
        """Check sync eligibility using pending values over stored values."""
        account = self.browse(cr, uid, id, context=context)
        vals = vals or {}
        code = vals['code'] if 'code' in vals else account.code
        odoo_account_code = (
            vals['odoo_account_code']
            if 'odoo_account_code' in vals else account.odoo_account_code
        )
        has_twelve_digit_code = bool(
            re.match(r'^[0-9]{12}\Z', code or '')
        )
        return has_twelve_digit_code and bool(odoo_account_code)

    def copy_data(self, cr, uid, id, default=None, context=None):
        account = self.browse(cr, uid, id, context=context)
        default = (default or {}).copy()
        default.update({
            'code': (account.code or '') + 'COPY',
            'odoo_account_code': False,
        })
        return super(AccountAccount, self).copy_data(
            cr, uid, id, default=default, context=context
        )

    def write(self, cr, uid, ids, vals, context=None):
        if context is None:
            context = {}
        if 'odoo_account_code' in vals:
            if not isinstance(ids, list):
                ids = [ids]
            new_odoo_account_code = vals['odoo_account_code'] or False
            sync_obj = self.pool.get('odoo.sync')
            for account in self.browse(cr, uid, ids, context=context):
                if account.odoo_account_code == new_odoo_account_code:
                    continue
                sync_ids = sync_obj.search(cr, uid, [
                    ('model.model', '=', self._name),
                    ('res_id', '=', account.id),
                ], limit=1, context=context)
                if sync_ids:
                    raise osv.except_osv(
                        'Error',
                        'The Odoo account code cannot be changed once the account '
                        'is linked to Odoo.',
                    )
        return super(AccountAccount, self).write(
            cr, uid, ids, vals, context=context
        )

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
