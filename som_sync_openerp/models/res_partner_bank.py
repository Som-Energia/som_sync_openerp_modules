#  -*- coding: utf-8 -*-
from osv import osv


class ResPartnerBank(osv.osv):
    _name = 'res.partner.bank'
    _inherit = 'res.partner.bank'

    MAPPING_FIELDS_TO_SYNC = {
        'partner_id': 'partner_id',
        'iban': 'acc_number',
        'id': 'pnt_erp_id',
    }
    MAPPING_FK = {
        'partner_id': 'res.partner',
    }
    MAPPING_CONSTANTS = {
    }

    def get_endpoint_suffix(self, cr, uid, id, context={}):
        sync_obj = self.pool.get('odoo.sync')
        bank = self.browse(cr, uid, id, context=context)
        sync_obj_id = sync_obj.search(
            cr, uid, [('model', '=', 'res.partner'), ('res_id', '=', bank.partner_id.id)])
        odoo_partner_id = sync_obj.read(cr, uid, sync_obj_id[0], ['odoo_id'])['odoo_id']
        if bank.partner_id:
            res = '{}?acc_number={}'.format(odoo_partner_id, bank.iban)
            return res
        else:
            return False

    def create(self, cr, uid, vals, context={}):
        ids = super(ResPartnerBank, self).create(cr, uid, vals, context=context)

        sync_obj = self.pool.get('odoo.sync')
        sync_obj.common_sync_model_create_update(
            cr, uid, self._name, ids, 'create', context=context
        )

        return ids


ResPartnerBank()
