#  -*- coding: utf-8 -*-
from oorq.decorators import job
from osv import osv
import json
from service.security import Sudo

from .odoo_exceptions import ForeingKeyNotAvailable

import logging


logger = logging.getLogger('openerp.odoo.sync')


class Norma57File(osv.osv):
    _name = 'norma57.file'
    _inherit = 'norma57.file'

    PAYMENT_ENTRY_ACCOUNT_DEBIT_CODE = '572.9'
    PAYMENT_ENTRY_ACCOUNT_CREDIT_CODE = '570.0'
    PAYMENT_ENTRY_ERP_ID_OFFSET = 900000000

    MAPPING_FIELDS_TO_SYNC = {
        'id': 'pnt_erp_id',
        'header_presentation_date': 'date',
    }
    MAPPING_FK = {}
    MAPPING_CONSTANTS = {
        'batch_type': 'inbound',
    }

    def get_mapping_model_post(self, cr, uid, id, context=None):
        return 'payment_orders'

    def get_sync_state_on_creation(self, cr, uid, id, context=None):
        return 'pending'

    def get_endpoint_odoo_record_suffix(self, cr, uid, id, odoo_id, context=None):
        return '/action-375/{}'.format(odoo_id)

    def _get_config_odoo_id(self, cr, uid, key, context=None):
        if context is None:
            context = {}
        conf_obj = self.pool.get('res.config')
        value = conf_obj.get(cr, uid, key, 0)
        try:
            return int(value)
        except (TypeError, ValueError):
            logger.warning('Invalid %s config value: %s', key, value)
            return 0

    def _get_destination_journal_odoo_id(self, cr, uid, context=None):
        journal_odoo_id = self._get_config_odoo_id(
            cr, uid, 'odoo_norma57_destination_journal', context=context)
        if not journal_odoo_id:
            raise Exception('odoo_norma57_destination_journal is not configured')
        return journal_odoo_id

    def _get_payment_method_line_odoo_id(self, cr, uid, context=None):
        payment_method_line_id = self._get_config_odoo_id(
            cr, uid, 'odoo_norma57_payment_method', context=context)
        if not payment_method_line_id:
            raise Exception('odoo_norma57_payment_method is not configured')
        return payment_method_line_id

    def _get_payment_entry_journal_odoo_id(self, cr, uid, context=None):
        journal_odoo_id = self._get_config_odoo_id(
            cr, uid, 'odoo_norma57_payment_entry_journal', context=context)
        if not journal_odoo_id:
            raise Exception('odoo_norma57_payment_entry_journal is not configured')
        return journal_odoo_id

    def _get_payment_entry_account_code_candidates(self, code):
        raw_code = (code or '').strip()
        normalized = raw_code.replace('.', '')
        candidates = [raw_code]
        if normalized and normalized not in candidates:
            candidates.append(normalized)
        for target_len in (6, 9):
            if normalized and len(normalized) < target_len:
                padded = normalized.ljust(target_len, '0')
                if padded not in candidates:
                    candidates.append(padded)
        return candidates

    def _get_payment_entry_account_odoo_id_by_code(self, cr, uid, code, context=None):
        if context is None:
            context = {}
        account_obj = self.pool.get('account.account')
        sync_obj = self.pool.get('odoo.sync')

        for candidate in self._get_payment_entry_account_code_candidates(code):
            account_ids = account_obj.search(cr, uid, [('code', '=', candidate)], context=context)
            if not account_ids:
                continue
            odoo_id = sync_obj.get_odoo_id_by_erp_id(
                cr, uid, 'account.account', account_ids[0])
            if odoo_id:
                return odoo_id
            raise ForeingKeyNotAvailable('account.account,{}'.format(account_ids[0]))

        raise Exception('Account code {} not found for Norma57 payment entry'.format(code))

    def _get_payment_entry_erp_id(self, norma57_id):
        return self.PAYMENT_ENTRY_ERP_ID_OFFSET + int(norma57_id)

    def _get_payment_entry_label(self, norma57_file):
        return '[REMESA] {}'.format(norma57_file.name or '')

    def _get_sync_record_id(self, cr, uid, erp_id, context=None):
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        sync_ids = sync_obj.search(cr, uid, [
            ('model.model', '=', self._name),
            ('res_id', '=', erp_id),
        ], limit=1, context=context)
        return sync_ids[0] if sync_ids else False

    def _update_payment_entry_sync_fields(
            self, cr, uid, sync_id, entry_odoo_id=False, last_result=False, context=None):
        if context is None:
            context = {}
        vals = {}
        if entry_odoo_id is not False:
            vals['pnt_norma57_payment_entry_odoo_id'] = entry_odoo_id
        if last_result is not False:
            vals['pnt_norma57_payment_entry_last_result'] = last_result
        if not vals:
            return False
        with Sudo(uid=1, gid=0):
            return self.pool.get('odoo.sync').write(cr, uid, [sync_id], vals, context=context)

    def _build_payment_entry_payload(self, cr, uid, norma57_file, context=None):
        if context is None:
            context = {}

        label = self._get_payment_entry_label(norma57_file)
        amount = round(sum([
            abs(line.amount) for line in norma57_file.lines if line.state == 'confirmed'
        ]), 2)
        if amount <= 0:
            raise Exception('Norma57 file has no positive confirmed amount for payment entry')

        debit_account_odoo_id = self._get_payment_entry_account_odoo_id_by_code(
            cr, uid, self.PAYMENT_ENTRY_ACCOUNT_DEBIT_CODE, context=context)
        credit_account_odoo_id = self._get_payment_entry_account_odoo_id_by_code(
            cr, uid, self.PAYMENT_ENTRY_ACCOUNT_CREDIT_CODE, context=context)

        return {
            'pnt_erp_id': self._get_payment_entry_erp_id(norma57_file.id),
            'number': label,
            'date': norma57_file.header_presentation_date,
            'journal_id': self._get_payment_entry_journal_odoo_id(cr, uid, context=context),
            'ref': label,
            'lines': [
                {
                    'account_id': debit_account_odoo_id,
                    'name': label,
                    'debit': amount,
                },
                {
                    'account_id': credit_account_odoo_id,
                    'name': label,
                    'credit': amount,
                },
            ],
        }

    def _create_payment_entry_in_odoo(self, cr, uid, payload, context=None):
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        odoo_id, response_text, url_base = sync_obj.create_odoo_record(
            cr, uid, 'account.move', payload, context=context)
        return {
            'success': bool(odoo_id),
            'odoo_id': odoo_id,
            'response_text': response_text,
            'url': url_base,
        }

    def _get_existing_payment_entry_odoo_id(self, cr, uid, payment_entry_erp_id, context=None):
        if context is None:
            context = {}
        sync_obj = self.pool.get('odoo.sync')
        return sync_obj.get_odoo_id_by_erp_id_from_odoo(
            cr, uid, 'account.move', payment_entry_erp_id)

    def _sync_norma57_payment_entry_if_needed(self, cr, uid, erp_id, context=None):
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        sync_id = self._get_sync_record_id(cr, uid, erp_id, context=context)
        if not sync_id:
            return False

        sync_record = sync_obj.browse(cr, uid, sync_id, context=context)
        if sync_record.sync_state != 'synced':
            return False
        if sync_record.pnt_norma57_payment_entry_odoo_id:
            return sync_record.pnt_norma57_payment_entry_odoo_id

        norma57_file = self.browse(cr, uid, erp_id, context=context)
        payload = self._build_payment_entry_payload(cr, uid, norma57_file, context=context)
        result = self._create_payment_entry_in_odoo(cr, uid, payload, context=context)
        if result['success'] and result['odoo_id']:
            self._update_payment_entry_sync_fields(
                cr,
                uid,
                sync_id,
                entry_odoo_id=result['odoo_id'],
                last_result=result['response_text'] or 'created',
                context=context,
            )
            return result['odoo_id']

        response_text = result.get('response_text') or ''
        existing_odoo_id = False
        if response_text:
            try:
                response_json = json.loads(response_text)
            except Exception:
                response_json = {}
            if response_json.get('error_code') == 'DUPLICATE_KEY_VALUE':
                existing_odoo_id = self._get_existing_payment_entry_odoo_id(
                    cr, uid, payload['pnt_erp_id'], context=context)

        if existing_odoo_id:
            self._update_payment_entry_sync_fields(
                cr,
                uid,
                sync_id,
                entry_odoo_id=existing_odoo_id,
                last_result=response_text or 'duplicate entry recovered',
                context=context,
            )
            return existing_odoo_id

        self._update_payment_entry_sync_fields(
            cr,
            uid,
            sync_id,
            last_result=response_text or 'Error creating Norma57 payment entry in Odoo',
            context=context,
        )
        return False

    def _get_line_invoice_erp_id(self, cr, uid, line, context=None):
        if context is None:
            context = {}
        if not line.resource:
            return False

        model, model_id = line.resource.split(',')
        if model == 'account.invoice':
            return int(model_id)

        if model != 'giscedata.facturacio.factura':
            logger.warning('Unsupported Norma57 resource: %s', line.resource)
            raise Exception('Unsupported Norma57 resource: {}'.format(line.resource))

        model_id = int(model_id)
        factura_obj = self.pool.get('giscedata.facturacio.factura')
        invoice_id = factura_obj.read(
            cr, uid, model_id, ['invoice_id'], context=context).get('invoice_id')
        if not invoice_id:
            return False
        return invoice_id[0]

    def _build_line_values(self, cr, uid, line, context=None):
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        invoice_erp_id = self._get_line_invoice_erp_id(cr, uid, line, context=context)
        if not invoice_erp_id:
            raise ForeingKeyNotAvailable('account.invoice,False')

        context_copy = context.copy()
        context_copy['from_fk_sync'] = True
        invoice_odoo_id, _ = sync_obj.common_sync_model_create_update(
            cr, uid, 'account.invoice', 'sync', invoice_erp_id, context_copy)
        if not invoice_odoo_id:
            raise ForeingKeyNotAvailable('account.invoice,{}'.format(invoice_erp_id))

        return {
            'invoice_id': invoice_odoo_id,
            'amount': abs(line.amount),
        }, invoice_erp_id

    def get_related_values(self, cr, uid, id, context=None):
        if context is None:
            context = {}

        norma57_file = self.browse(cr, uid, id, context=context)
        inv_obj = self.pool.get('account.invoice')
        destination_journal_id = self._get_destination_journal_odoo_id(
            cr, uid, context=context)
        payment_method_line_id = self._get_payment_method_line_odoo_id(
            cr, uid, context=context)
        lines = []
        invoice_ids = []

        for line in norma57_file.lines:
            if line.state != 'confirmed':
                continue
            line_vals, invoice_id = self._build_line_values(cr, uid, line, context=context)
            lines.append(line_vals)
            invoice_ids.append(invoice_id)

        if not lines:
            raise Exception('Norma57 file has no syncable confirmed invoice lines')

        inv_obj.process_lines_with_discrepancies(
            cr, uid, invoice_ids, lines, is_grouped=False, context=context)

        total_amount = round(sum([line['amount'] for line in lines]), 2)

        return {
            'destination_journal_id': destination_journal_id,
            'payment_method_line_id': payment_method_line_id,
            'name': norma57_file.name or '',
            'sdd_required_collection_date': norma57_file.header_presentation_date,
            'amount': total_amount,
            'lines': lines,
        }

    def check_special_restrictions(self, cr, uid, id, context=None):
        if context is None:
            context = {}
        norma57_file = self.browse(cr, uid, id, context=context)
        return any([line.state == 'confirmed' for line in norma57_file.lines])

    def confirm(self, cursor, uid, ids, context=None):
        if context is None:
            context = {}

        res = super(Norma57File, self).confirm(cursor, uid, ids, context=context)

        if not isinstance(ids, (list, tuple)):
            ids = [ids]

        with Sudo(uid=1, gid=0):
            sync_obj = self.pool.get('odoo.sync')
            for norma57_id in ids:
                sync_obj.common_sync_model_create_update(
                    cursor, uid, 'norma57.file', 'write', norma57_id, context=context)

        return res

    @job(queue='sync_odoo', timeout=3600)
    def update_pending_state(self, cursor, uid, openerp_id, context=None):
        if context is None:
            context = {}
        self.update_pending_state_sync(cursor, uid, openerp_id, context=context)

    def update_pending_state_sync(self, cr, uid, erp_id, context=None):
        if context is None:
            context = {}

        sync_obj = self.pool.get('odoo.sync')
        result = sync_obj.poll_payment_order_status_sync(
            cr, uid, self._name, erp_id, context=context)
        if result:
            self._sync_norma57_payment_entry_if_needed(cr, uid, erp_id, context=context)
        return result


Norma57File()
