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
        account = self.browse(cr, uid, id, context=context)
        return len(account.code or '') != 12 or bool(account.odoo_account_code)

    def copy(self, cr, uid, id, default=None, context=None,
             done_list=None, local=False):
        context = context or {}
        confirmed = context.get('account_copy_defaults', {}).get(str(id))
        account = self.browse(cr, uid, id, context=context)
        requires_confirmation = len(account.code or '') == 12 or account.odoo_account_code
        if requires_confirmation and (
                not confirmed or not confirmed.get('code')
                or 'odoo_account_code' not in confirmed):
            raise osv.except_osv(
                'Error',
                'Use the "Duplicate account..." action to confirm the new '
                'account codes before creating and synchronizing the account.',
            )
        if confirmed is not None:
            default = (default or {}).copy()
            # Legacy recursion passes the parent's defaults to every child.
            # Use this account's codes. Apply wizard name changes only in
            # copy_data(), after the children have been copied, so the name
            # cannot leak to children or replace other extensions' defaults.
            for field in ('code', 'odoo_account_code'):
                if field in confirmed:
                    default[field] = confirmed[field]
        return super(AccountAccount, self).copy(
            cr, uid, id, default=default, context=context,
            done_list=done_list if done_list is not None else [], local=local,
        )

    def copy_data(self, cr, uid, id, default=None, context=None):
        confirmed = (context or {}).get('account_copy_defaults', {}).get(str(id))
        if confirmed is not None:
            if default is None:
                default = {}
            # account.copy() replaces code with '(copy)' before calling this hook.
            # Update this same dict so ORM.copy() also excludes these overrides
            # when copying translations, just as for ordinary copy defaults.
            default.update(confirmed)
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
        if 'account_copy_defaults' in context:
            context = context.copy()
            del context['account_copy_defaults']
        ids = super(AccountAccount, self).create(cr, uid, vals, context=context)

        with Sudo(uid=1, gid=0):
            sync_obj = self.pool.get('odoo.sync')
            sync_obj.common_sync_model_create_update(
                cr, uid, self._name, 'create', ids, context=context
            )

        return ids


AccountAccount()
