#  -*- coding: utf-8 -*-
from osv import osv


class ResMunicipi(osv.osv):
    _name = 'res.municipi'
    _inherit = 'res.municipi'

    MAPPING_FIELDS_TO_SYNC = {
        'name': 'name',
        'ine': 'pnt_code_ine',
    }
    MAPPING_FK = {
    }
    MAPPING_CONSTANTS = {
    }

    def get_endpoint_suffix(self, cr, uid, id, context={}):
        municipi = self.browse(cr, uid, id, context=context)
        if municipi.ine:
            res = '{}'.format(municipi.ine)
            return res
        else:
            return False


ResMunicipi()
