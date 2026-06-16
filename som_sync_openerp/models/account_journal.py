#  -*- coding: utf-8 -*-
from osv import osv, fields


class AccountJournal(osv.osv):
    _name = 'account.journal'
    _inherit = 'account.journal'

    _columns = {
        'som_sync_odoo_account_moves': fields.boolean(
            'Sync with Odoo Account Moves',
            help='If checked, this journal will be synchronize Moves with Odoo.'),
        'som_sync_odoo_invoices': fields.boolean(
            'Sync with Odoo Invoices',
            help='If checked, this journal will be synchronize Invoices with Odoo.'),
        'company_partner_id': fields.related(
            'company_id', 'partner_id',
            type='many2one', relation='res.partner',
            string='Company Partner', readonly=True,
        ),
        'company_bank_id': fields.many2one(
            'res.partner.bank', 'Bank account for Odoo sync',
            domain="[('partner_id', '=', company_partner_id)]",
            help='Bank account used to resolve the Odoo journal for payment order sync.'),
    }

    _defaults = {
        'som_sync_odoo_account_moves': lambda *a, **k: False,
        'som_sync_odoo_invoices': lambda *a, **k: False,
    }

    _sql_constraints = [
        (
            'company_bank_id_unique',
            'unique(company_bank_id)',
            'A bank account can only be linked to one journal.',
        ),
    ]


AccountJournal()
