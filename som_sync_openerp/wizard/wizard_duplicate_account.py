# -*- coding: utf-8 -*-
import re

from osv import osv, fields


class WizardDuplicateAccountLine(osv.osv_memory):
    _name = 'wizard.duplicate.account.line'
    _description = 'Confirmed codes for a child account copy'

    _columns = {
        'wizard_id': fields.many2one('wizard.duplicate.account', 'Wizard'),
        'account_id': fields.many2one(
            'account.account', 'Source child account', required=True, readonly=True,
        ),
        'code': fields.char('New account code', size=64, required=True),
        'odoo_account_code': fields.char('Odoo account code', size=9),
    }


WizardDuplicateAccountLine()


class WizardDuplicateAccount(osv.osv_memory):
    _name = 'wizard.duplicate.account'
    _description = 'Duplicate an account with confirmed Odoo mapping'

    def _get_copy_accounts(self, cr, uid, account_id, context=None):
        account_obj = self.pool.get('account.account')
        accounts, seen = [], set()
        pending = [account_id]
        while pending:
            source_id = pending.pop()
            if source_id in seen:
                continue
            seen.add(source_id)
            account = account_obj.browse(cr, uid, source_id, context=context)
            accounts.append(account)
            # Match account.copy(): include both hierarchy and consolidation children.
            pending.extend(child.id for child in reversed(account.child_id))
        return accounts

    def default_get(self, cr, uid, fields_list, context=None):
        context = context or {}
        account_ids = context.get('active_ids') or []
        if not account_ids and context.get('active_id'):
            account_ids = [context['active_id']]
        if (context.get('active_model', 'account.account') != 'account.account'
                or len(account_ids) != 1):
            raise osv.except_osv('Error', 'Select exactly one account to duplicate.')
        account = self.pool.get('account.account').browse(
            cr, uid, account_ids[0], context=context
        )
        values = super(WizardDuplicateAccount, self).default_get(
            cr, uid, fields_list, context=context
        )
        defaults = {
            'account_id': account.id,
            'name': account.name,
            'code': False,
            'odoo_account_code': False,
        }
        if 'line_ids' in fields_list or 'has_children' in fields_list:
            children = self._get_copy_accounts(
                cr, uid, account.id, context=context
            )[1:]
            defaults['has_children'] = bool(children)
            defaults['line_ids'] = [(0, 0, {
                'account_id': child.id, 'code': False, 'odoo_account_code': False,
            }) for child in children]
        values.update((key, value) for key, value in defaults.items()
                      if key in fields_list)
        return values

    def _confirmed_codes(self, account, code, mapping):
        if not code:
            raise osv.except_osv(
                'Error', 'Specify a new code for account %s.' % account.code
            )
        if len(code) == 12 and not mapping:
            raise osv.except_osv(
                'Error', 'Accounts with a 12-digit code require an Odoo account code.'
            )
        if mapping and not re.match(r'^[0-9]{9}\Z', mapping):
            raise osv.except_osv(
                'Error', 'The Odoo account code must contain exactly 9 digits.'
            )
        return {'code': code, 'odoo_account_code': mapping or False}

    def action_duplicate(self, cr, uid, ids, context=None):
        if len(ids) != 1:
            raise osv.except_osv('Error', 'Confirm exactly one duplication at a time.')
        wizard = self.browse(cr, uid, ids[0], context=context)
        if not wizard.account_id or not wizard.name or not wizard.code:
            raise osv.except_osv(
                'Error', 'Specify the source account, name and new account code.'
            )
        account_obj = self.pool.get('account.account')
        sources = self._get_copy_accounts(
            cr, uid, wizard.account_id.id, context=context
        )
        expected_ids = set(account.id for account in sources[1:])
        provided_ids = [line.account_id.id for line in wizard.line_ids]
        if set(provided_ids) != expected_ids or len(provided_ids) != len(expected_ids):
            raise osv.except_osv(
                'Error', 'The child accounts have changed. Reopen the duplication wizard.'
            )
        overrides = {str(wizard.account_id.id): self._confirmed_codes(
            wizard.account_id, wizard.code, wizard.odoo_account_code
        )}
        if wizard.name != wizard.account_id.name:
            overrides[str(wizard.account_id.id)]['name'] = wizard.name
        for line in wizard.line_ids:
            overrides[str(line.account_id.id)] = self._confirmed_codes(
                line.account_id, line.code, line.odoo_account_code
            )
        copy_context = dict(context or {})
        copy_context['account_copy_defaults'] = overrides
        # Keep the complete copy chain, including children, translations and extensions.
        root_defaults = overrides[str(wizard.account_id.id)].copy()
        root_defaults.pop('name', None)
        account_id = account_obj.copy(
            cr, uid, wizard.account_id.id,
            default=root_defaults, context=copy_context,
        )
        return {
            'name': 'Duplicated account',
            'type': 'ir.actions.act_window',
            'res_model': 'account.account',
            'res_id': account_id,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'current',
        }

    _columns = {
        'account_id': fields.many2one(
            'account.account', 'Source account', required=True, readonly=True,
        ),
        'name': fields.char('New account name', size=128, required=True),
        'code': fields.char('New account code', size=64, required=True),
        'odoo_account_code': fields.char('Odoo account code', size=9),
        'has_children': fields.boolean('Has child accounts', readonly=True),
        'line_ids': fields.one2many(
            'wizard.duplicate.account.line', 'wizard_id', 'Child accounts',
        ),
    }


WizardDuplicateAccount()
