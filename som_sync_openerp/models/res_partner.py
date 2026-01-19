#  -*- coding: utf-8 -*-
from osv import osv


class ResPartner(osv.osv):
    _name = 'res.partner'
    _inherit = 'res.partner'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'name',
        'lang': 'lang',
        'vat': 'vat',
        'customer': 'is_customer',
        # 'supplier': 'is_supplier',
        # 'type': 'type', not mapped, is a constant
        # 'property_account_position_id': 'property_account_position_id', #'fiscal_position'
        # 'property_payment_term_id': 'property_payment_term_id', #'payment_term'
        'property_account_receivable': 'property_account_receivable_id',  # 'account_receivable
        'property_account_payable': 'property_account_payable_id',  # 'account_payable'
        'property_account_position': 'property_account_position_id',
        'property_payment_term': 'property_payment_term_id',
        # 'id': 'pnt_erp_id',
    }

    MAPPING_FK = {
        # 'property_payment_term_id': 'account.payment.term', #'payment_term'
        'property_account_receivable': 'account.account',  # 'account_receivable
        'property_account_payable': 'account.account',  # 'account_payable'
        'property_account_position': 'account.fiscal.position',  # 'account.fiscal.position'
        'property_payment_term': 'account.payment.term',  # 'account.payment.term'
    }

    MAPPING_CONSTANTS = {
        'type': 'contact',
        'is_company': True,
    }

    def get_endpoint_suffix(self, cr, uid, id, context={}):
        partner = self.browse(cr, uid, id, context=context)
        if partner.vat:
            res = 'company/{}'.format(partner.vat)
            return res
        else:
            return False

    def create(self, cr, uid, vals, context={}):
        ids = super(ResPartner, self).create(cr, uid, vals, context=context)

        sync_obj = self.pool.get('odoo.sync')
        sync_obj.syncronize(
            cr, uid, self._name, 'create', ids, context=context)

        return ids


ResPartner()
