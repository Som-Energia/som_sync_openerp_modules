#  -*- coding: utf-8 -*-
from osv import osv


class ResCountry(osv.osv):
    _name = 'res.country'
    _inherit = 'res.country'

    MAPPING_FIELDS_TO_SYNC = {
        'name': 'name',
        'code': 'code',
    }
    MAPPING_FK = {
    }
    MAPPING_CONSTANTS = {
    }

    def get_endpoint_suffix(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        country = self.browse(cr, uid, id, context=context)
        if country.code:
            res = '{}'.format(country.code)
            return res
        else:
            return False

    def create(self, cr, uid, vals, context=None):
        if context is None:
            context = {}
        ids = super(ResCountry, self).create(cr, uid, vals, context=context)

        sync_obj = self.pool.get('odoo.sync')
        sync_obj.common_sync_model_create_update(
            cr, uid, self._name, 'create', ids, context=context
        )

        return ids


ResCountry()
