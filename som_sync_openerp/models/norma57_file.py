#  -*- coding: utf-8 -*-
from osv import osv


class Norma57File(osv.osv):
    _name = 'norma57.file'
    _inherit = 'norma57.file'

    def confirm(self, cursor, uid, ids, context=None):
        if context is None:
            context = {}

        payment_context = context.copy()
        payment_context['skip_bank_statement_line_payment_sync'] = True
        res = super(Norma57File, self).confirm(
            cursor, uid, ids, context=payment_context)

        return res


Norma57File()
