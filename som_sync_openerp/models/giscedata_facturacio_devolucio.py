#  -*- coding: utf-8 -*-
from osv import osv


class GiscedataFacturacioDevolucio(osv.osv):
    _name = 'giscedata.facturacio.devolucio'
    _inherit = 'giscedata.facturacio.devolucio'

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'name': 'name',
        'date': 'date',
        'pay_journal_id': 'journal_id',
        'pay_account_id': 'account_id',
    }
    MAPPING_FK = {
        'pay_account_id': 'account.account',
        'pay_journal_id': 'account.journal',
    }
    MAPPING_CONSTANTS = {
    }

    def get_endpoint_odoo_record_suffix(self, cr, uid, id, odoo_id, context=None):
        """
        This method is used to get the suffix to identify the record in Odoo
        - for customer: :/odoo/action-639/1
        """
        if context is None:
            context = {}
        return '/odoo/action-639/{}'.format(odoo_id)

    def get_syncable_devolucio_ids(self, cr, uid, context=None):
        """
        Return devolucio ids that meet these constraints:
        - They have at least ``min_lines`` lines and at most ``max_lines`` lines.
        - Every linked invoice (by ``numfactura``) is remesed
          (has ``payment_order_id``) in a remesa with fewer than
          ``max_invoices_per_remesa`` invoices.

        Preferred input is via context keys:
        - context['syncable_min_lines']
        - context['syncable_max_lines']
        - context['syncable_max_invoices_per_remesa']
        - context['syncable_candidate_domain'] (optional domain for initial search)

        Example of use:
        context = {
            'syncable_min_lines': 1,
            'syncable_max_lines': 2,
            'syncable_max_invoices_per_remesa': 1500,
            'syncable_candidate_domain': [('date', '>=', '2025-01-01')],
        }
        """
        if context is None:
            context = {}

        min_lines = context.get('syncable_min_lines', 1)
        max_lines = context.get('syncable_max_lines', 2)
        max_invoices_per_remesa = context.get('syncable_max_invoices_per_remesa', 1500)
        candidate_domain = context.get('syncable_candidate_domain', [])

        ids = self.search(cr, uid, candidate_domain, context=context)
        if not isinstance(ids, list):
            ids = [ids]

        dev_lin_obj = self.pool.get('giscedata.facturacio.devolucio.linia')
        inv_obj = self.pool.get('account.invoice')

        valid_devolucio_ids = []
        remesa_invoice_count_cache = {}

        for devolucio_id in ids:
            print('Checking devolucio_id', devolucio_id)  # TODO: remove debug print
            dev_lin_ids = dev_lin_obj.search(
                cr, uid, [('devolucio_id', '=', devolucio_id)], context=context)

            if not dev_lin_ids or len(dev_lin_ids) > max_lines or len(dev_lin_ids) < min_lines:
                continue

            numfacts = dev_lin_obj.read(
                cr, uid, dev_lin_ids, ['numfactura'], context=context)

            is_valid = True
            for numfact in numfacts:
                invoice_number = numfact.get('numfactura', False)
                if not invoice_number:
                    is_valid = False
                    break

                invoice_ids = inv_obj.search(
                    cr, uid, [('number', '=', invoice_number)], limit=1, context=context)
                if not invoice_ids:
                    is_valid = False
                    break

                invoice_data = inv_obj.read(
                    cr, uid, invoice_ids[0], ['payment_order_id'], context=context)
                remesa_data = invoice_data.get('payment_order_id', False)
                if not remesa_data:
                    is_valid = False
                    break

                remesa_id = remesa_data[0]
                if remesa_id not in remesa_invoice_count_cache:
                    remesa_invoice_ids = inv_obj.search(
                        cr, uid, [('payment_order_id', '=', remesa_id)], context=context)
                    remesa_invoice_count_cache[remesa_id] = len(remesa_invoice_ids)

                if remesa_invoice_count_cache[remesa_id] >= max_invoices_per_remesa:
                    is_valid = False
                    break

            if is_valid:
                print('Devolucio_id', devolucio_id, 'is valid')  # TODO: remove debug print
                valid_devolucio_ids.append(devolucio_id)

        return valid_devolucio_ids

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        inv_obj = self.pool.get('account.invoice')
        dev_lin_obj = self.pool.get('giscedata.facturacio.devolucio.linia')

        lines = []

        context_copy = context.copy()
        context_copy['from_fk_sync'] = True
        # we get the lines from 'numfactura' from devolucio lines
        dev_lin_ids = dev_lin_obj.search(cr, uid, [('devolucio_id', '=', id)])
        numfacts = dev_lin_obj.read(cr, uid, dev_lin_ids, ['numfactura', 'import'])
        invoice_ids = []
        for numfact in numfacts:
            invoice_id = inv_obj.search(cr, uid, [('number', '=', numfact['numfactura'])])
            if invoice_id:
                invoice_id = invoice_id[0]
                odoo_id, _ = sync_obj.common_sync_model_create_update(
                    cr, uid, 'account.invoice', 'sync', invoice_id, context_copy)
                line = {
                    'invoice_id': odoo_id,
                    'amount': numfact['import'],  # TODO: control invoices with discrepancies
                }
                lines.append(line)
                invoice_ids.append(invoice_id)

        inv_obj.process_lines_with_discrepancies(
            cr, uid, invoice_ids, lines, is_grouped=False, context=context
        )

        total_amount = 0
        for line in lines:
            total_amount += line['amount']
        total_amount = round(total_amount, 2)

        res = {
            'lines': lines,
            'amount': total_amount,
        }
        return res


GiscedataFacturacioDevolucio()
