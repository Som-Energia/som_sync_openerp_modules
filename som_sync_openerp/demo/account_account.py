#  -*- coding: utf-8 -*-
from osv import osv


class AccountAccount(osv.osv):
    _name = 'account.account'
    _inherit = 'account.account'

    def ensure_demo_account_iva(self, cr, uid, context=None):
        if context is None:
            context = {}

        imd_obj = self.pool.get('ir.model.data')
        account_type_id = imd_obj.get_object_reference(
            cr, uid, 'som_sync_openerp', 'financieras'
        )[1]
        values = {
            'name': 'Compte IVA per linia IESE',
            'code': '475600',
            'user_type': account_type_id,
            'company_id': 1,
            'currency_mode': 'current',
            'type': 'other',
        }
        xml_account_id = False
        try:
            xml_account_id = imd_obj.get_object_reference(
                cr, uid, 'som_sync_openerp', 'account_account_iva'
            )[1]
        except ValueError:
            pass

        if xml_account_id:
            xml_account_ids = self.search(
                cr, uid, [('id', '=', xml_account_id)], context=context
            )
            if xml_account_ids:
                return imd_obj._update(
                    cr, uid, self._name, 'som_sync_openerp', values,
                    xml_id='account_account_iva', res_id=xml_account_id,
                    noupdate=False, mode='init', context=context
                )
            stale_imd_id = imd_obj._get_id(
                cr, uid, 'som_sync_openerp', 'account_account_iva'
            )
            if stale_imd_id:
                imd_obj.unlink(cr, uid, [stale_imd_id], context=context)

        account_ids = self.search(
            cr, uid, [('code', '=', '475600'), ('company_id', '=', 1)], context=context
        )

        if account_ids:
            imd_obj._update(
                cr, uid, self._name, 'som_sync_openerp', {},
                xml_id='account_account_iva', res_id=account_ids[0],
                noupdate=False, mode='init', context=context
            )
            return account_ids[0]

        return imd_obj._update(
            cr, uid, self._name, 'som_sync_openerp', values,
            xml_id='account_account_iva', noupdate=False,
            mode='init', context=context
        )


AccountAccount()
