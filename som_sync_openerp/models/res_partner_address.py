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
        'nv': 'street',
        'zip': 'zip',
        'partner_id': 'parent_id',
        'state_id': 'state_id',
        'city': 'city',
    }

    MAPPING_FK = {
        'state_id': 'res.country.state',
        'country_id': 'res.country',
        'partner_id': 'res.partner',
    }

    MAPPING_CONSTANTS = {
        'type': 'invoice',
        'is_company': False,
    }

    def get_related_values(self, cr, uid, id, context={}):
        address = self.browse(cr, uid, id, context=context)
        res = {
            'is_customer': address.partner_id.customer,
            'is_supplier': address.partner_id.supplier,
            'lang': address.partner_id.lang,
        }
        return res

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

        sync_obj = self.pool.get('odoo.sync')
        sync_obj.common_sync_model_create_update(
            cr, uid, self._name, ids, 'create', context=context
        )

        return ids

    def write(self, cr, uid, ids, vals, context={}):
        if context is None:
            context = {}
        if not isinstance(ids, list):
            ids = [ids]

        res = super(ResPartnerAddress, self).write(cr, uid, ids, vals, context=context)

        # we check if any of the fields to sync is in vals
        if any(field in vals.keys() for field in self.MAPPING_FIELDS_TO_SYNC.keys()):
            sync_obj = self.pool.get('odoo.sync')
            sync_obj.common_sync_model_create_update(
                cr, uid, self._name, ids, 'write', context=context
            )

        return res


ResPartnerAddress()
