#  -*- coding: utf-8 -*-
from osv import osv


class ResCountryState(osv.osv):
    _name = 'res.country.state'
    _inherit = 'res.country.state'

    MAPPING_FIELDS_TO_SYNC = {
        'name': 'name',
        'ree_code': 'code',
        'country_id': 'country_id',
        'id': 'pnt_erp_id',
    }
    MAPPING_FK = {
        'country_id': 'res.country',
    }
    MAPPING_CONSTANTS = {
    }

    def get_endpoint_suffix(self, cr, uid, id, context={}):
        state = self.browse(cr, uid, id, context=context)
        if state.ree_code and state.country_id:
            res = '{}/{}'.format(state.country_id.code, state.ree_code)
            return res
        else:
            return False

    def create(self, cr, uid, vals, context={}):
        ids = super(ResCountryState, self).create(cr, uid, vals, context=context)

        sync_obj = self.pool.get('odoo.sync')
        sync_obj.common_sync_model_create_update(
            cr, uid, self._name, ids, 'create', context=context
        )

        return ids


ResCountryState()
