# -*- coding: utf-8 -*-
from oorq.decorators import job
from osv import osv


class Norma57FileLine(osv.osv):
    _name = 'norma57.file.line'
    _inherit = 'norma57.file.line'

    @job(queue='sync_odoo', timeout=3600)
    def update_pending_state(self, cursor, uid, line_id, context=None):
        if context is None:
            context = {}
        line = self.browse(cursor, uid, line_id, context=context)
        if line.state != 'confirmed':
            return False
        return self.pool.get('norma57.file').sync_bank_statement_lines(
            cursor, uid, line.file_id.id, context=context)


Norma57FileLine()
