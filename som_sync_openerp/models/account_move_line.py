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
    ONLY_MOVES_FIELDS_TO_SYNC = dict(
        MAPPING_FIELDS_TO_SYNC, analytic_account_id='analytic_account_id')
    MAPPING_FK = {
        'account_id': 'account.account',
        'partner_id': 'res.partner',
        'analytic_account_id': 'account.analytic.account',
    }
    MAPPING_CONSTANTS = {
    }

    def get_default_sync_fk(self, cr, uid, line_id, field, context=None):
        """Return a local default FK for export without changing the source line."""
        if field != 'analytic_account_id' or \
                self.pool.get('odoo.sync')._get_profile(context) != 'only_moves':
            return False
        line = self.browse(cr, uid, line_id, context=context)
        default_obj = self.pool.get('account.analytic.default')
        domain = default_obj.domain_get(
            account_id=line.account_id.id,
            partner_id=line.partner_id.id, product_id=line.product_id.id,
            user_id=uid, date=line.date, context=context)
        # The ERP omits this constraint for a missing product, admitting rules
        # for unrelated products. Filter candidates before choosing the winner.
        if not line.product_id:
            domain.append(('product_id', '=', False))
        rule_ids = default_obj.search(cr, uid, domain, context=context)
        rules = default_obj.browse(cr, uid, rule_ids, context=context)
        default = max(rules, key=default_obj.best_index_get) if rules else False
        return default.analytic_id.id if default and default.analytic_id else False

    def hook_last_modifications(self, cr, uid, data, context=None):
        if context is None:
            context = {}
        if self.pool.get('odoo.sync')._get_profile(context) == 'only_moves' and \
                not data.get('analytic_account_id'):
            data.pop('analytic_account_id', None)
        data['name'] = data.get('ref', False) or data.get('name', '')
        data.pop('ref', False)
        return data


AccountMoveLine()
