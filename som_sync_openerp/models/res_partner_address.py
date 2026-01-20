#  -*- coding: utf-8 -*-
from osv import osv


class ResPartnerAddress(osv.osv):
    _name = 'res.partner.address'
    _inherit = 'res.partner.address'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'name',
        'email': 'email',
        'phone': 'phone',
        'street': 'street',
        'zip': 'code_zip',
        'partner_id': 'parent_id',
        'state_id': 'state_id',
        # 'country_id': 'country_id',
    }
    MAPPING_FK = {
        'state_id': 'res.country.state',
        # 'country_id': 'res.country',
        'partner_id': 'res.partner',
    }

    MAPPING_CONSTANTS = {
        'type': 'invoice',
        'is_company': False,
        # TODO: Not lang in partner.address, worthit get it from partner?
        'lang': 'ca_ES',
    }

    def get_endpoint_suffix(self, cr, uid, id, context={}):
        # /contact/{parent_id}/{ttype}
        address = self.browse(cr, uid, id, context=context)
        sync_obj = self.pool.get('odoo.sync')
        sync_parent_ids = sync_obj.search(cr, uid, [
            ('model', '=', 'res.partner'),
            ('res_id', '=', address.partner_id.id),
        ])
        if sync_parent_ids:
            parent_odoo_id = sync_obj.read(
                cr, uid, sync_parent_ids[0], ['odoo_id'])['odoo_id']
            res = 'contact/{}/{}'.format(parent_odoo_id, 'invoice')
            return res
        else:
            return False

    def create(self, cr, uid, vals, context={}):
        ids = super(ResPartnerAddress, self).create(cr, uid, vals, context=context)

        # sync_obj = self.pool.get('odoo.sync')
        # sync_obj.syncronize_sync(
        #     cr, uid, self._name, 'create', ids, context=context)

        return ids


ResPartnerAddress()
