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
        'supplier': 'is_supplier',
        'property_account_receivable': 'property_account_receivable_id',  # 'account_receivable
        'property_account_payable': 'property_account_payable_id',  # 'account_payable'
        'property_account_position': 'property_account_position_id',  # 'account.fiscal.position'
        'property_payment_term': 'property_payment_term_id',  # 'account.payment.term'
        'payment_type_customer': 'property_inbound_payment_method_line_id',  # 'payment.type'
        'payment_type_supplier': 'property_outbound_payment_method_line_id',  # 'payment.type'
    }

    MAPPING_FK = {
        'property_account_receivable': 'account.account',  # 'account_receivable
        'property_account_payable': 'account.account',  # 'account_payable'
        'property_account_position': 'account.fiscal.position',  # 'account.fiscal.position'
        'property_payment_term': 'account.payment.term',  # 'account.payment.term'
        'payment_type_customer': 'payment.type',  # 'payment.type'
        'payment_type_supplier': 'payment.type',  # 'payment.type'
    }

    MAPPING_CONSTANTS = {
        'type': 'contact',
        'is_company': True,
    }

    def get_endpoint_suffix(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        partner = self.browse(cr, uid, id, context=context)
        if partner.vat:
            res = 'company/{}'.format(partner.vat.upper())
            return res
        else:
            return False

    def create(self, cr, uid, vals, context=None):
        if context is None:
            context = {}
        ids = super(ResPartner, self).create(cr, uid, vals, context=context)

        sync_obj = self.pool.get('odoo.sync')
        sync_obj.common_sync_model_create_update(
            cr, uid, self._name, 'create', ids, context=context
        )

        return ids

    def hook_last_modifications(self, cr, uid, data, context=None):
        """
        Modify the data to ensure vat lettres are uppercase

        :param self: Description
        :param cr: Description
        :param uid: Description
        :param data: Description
        :param context: Description
        """
        if context is None:
            context = {}
        if data['vat']:
            data['vat'] = data['vat'].upper()
        return data


ResPartner()
