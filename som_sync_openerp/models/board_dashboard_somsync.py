#  -*- coding: utf-8 -*-
from osv import osv, fields


class BoardDashboardSomsync(osv.osv):
    _name = 'board.dashboard.somsync'
    _description = 'Dashboard Sincronització OpenERP-Odoo'
    _rec_name = 'display_name'

    def _get_date_start(self, cr, uid, context=None):
        return '2026-01-01'

    def _compute_total_invoices_syncable(self, cr, uid, ids, field_names, arg, context=None):
        if context is None:
            context = {}
        date_start = self._get_date_start(cr, uid, context)
        res = {}
        for record_id in ids:
            cr.execute("""
                SELECT COUNT(*)
                FROM account_invoice ai
                INNER JOIN account_journal aj ON ai.journal_id = aj.id
                WHERE aj.som_sync_odoo_invoices = True
                  AND ai.state IN ('open', 'paid')
                  AND ai.date_invoice >= %s
            """, (date_start,))
            res[record_id] = cr.fetchone()[0]
        return res

    def _compute_total_invoices_synced(self, cr, uid, ids, field_names, arg, context=None):
        if context is None:
            context = {}
        date_start = self._get_date_start(cr, uid, context)
        res = {}
        model_id = self._get_model_id(cr, uid, 'account.invoice')
        if not model_id:
            for record_id in ids:
                res[record_id] = 0
            return res
        for record_id in ids:
            cr.execute("""
                SELECT COUNT(*)
                FROM odoo_sync osync
                INNER JOIN account_invoice ai ON osync.res_id = ai.id
                WHERE osync.model = %s
                  AND osync.sync_state IN ('synced', 'synced_with_warning')
                  AND ai.date_invoice >= %s
            """, (model_id, date_start))
            res[record_id] = cr.fetchone()[0]
        return res

    def _compute_total_moves_syncable(self, cr, uid, ids, field_names, arg, context=None):
        if context is None:
            context = {}
        date_start = self._get_date_start(cr, uid, context)
        res = {}
        for record_id in ids:
            cr.execute("""
                SELECT COUNT(*)
                FROM account_move am
                INNER JOIN account_journal aj ON am.journal_id = aj.id
                WHERE aj.som_sync_odoo_account_moves = True
                  AND am.date >= %s
            """, (date_start,))
            res[record_id] = cr.fetchone()[0]
        return res

    def _compute_total_moves_synced(self, cr, uid, ids, field_names, arg, context=None):
        if context is None:
            context = {}
        date_start = self._get_date_start(cr, uid, context)
        res = {}
        model_id = self._get_model_id(cr, uid, 'account.move')
        if not model_id:
            for record_id in ids:
                res[record_id] = 0
            return res
        for record_id in ids:
            cr.execute("""
                SELECT COUNT(*)
                FROM odoo_sync osync
                INNER JOIN account_move am ON osync.res_id = am.id
                WHERE osync.model = %s
                  AND osync.sync_state IN ('synced', 'synced_with_warning')
                  AND am.date >= %s
            """, (model_id, date_start))
            res[record_id] = cr.fetchone()[0]
        return res

    def _get_model_id(self, cr, uid, model_name):
        cr.execute(
            "SELECT id FROM ir_model WHERE model = %s", (model_name,)
        )
        row = cr.fetchone()
        return row[0] if row else None

    def _compute_totals(self, cr, uid, ids, field_names, arg, context=None):
        res = {}
        syncable_inv = self._compute_total_invoices_syncable(
            cr, uid, ids, field_names, arg, context
        )
        synced_inv = self._compute_total_invoices_synced(
            cr, uid, ids, field_names, arg, context
        )
        syncable_mov = self._compute_total_moves_syncable(
            cr, uid, ids, field_names, arg, context
        )
        synced_mov = self._compute_total_moves_synced(
            cr, uid, ids, field_names, arg, context
        )
        for record_id in ids:
            syncable = syncable_inv[record_id] + syncable_mov[record_id]
            synced = synced_inv[record_id] + synced_mov[record_id]
            res[record_id] = {
                'total_invoices_syncable': syncable_inv[record_id],
                'total_invoices_synced': synced_inv[record_id],
                'total_moves_syncable': syncable_mov[record_id],
                'total_moves_synced': synced_mov[record_id],
                'total_syncable': syncable,
                'total_synced': synced,
                'pct_synced': round(
                    (synced * 100.0 / syncable) if syncable else 0.0, 2
                ),
            }
        return res

    _columns = {
        'display_name': fields.char('Nom', size=128),
        'date_start': fields.char(
            'Data inici', size=10,
            help='Data de inici per al filtre (AAAA-MM-DD)',
        ),
        'total_invoices_syncable': fields.integer(
            'Factures sincronitzables',
        ),
        'total_invoices_synced': fields.integer(
            'Factures sincronitzades',
        ),
        'total_moves_syncable': fields.integer(
            'Assentaments sincronitzables',
        ),
        'total_moves_synced': fields.integer(
            'Assentaments sincronitzats',
        ),
        'total_syncable': fields.integer(
            'Total sincronitzables',
        ),
        'total_synced': fields.integer(
            'Total sincronitzats',
        ),
        'pct_synced': fields.float(
            '% Sincronitzats',
        ),
    }

    _defaults = {
        'display_name': 'Dashboard Sincronització',
        'date_start': lambda obj, cr, uid, c: '2026-01-01',
        'total_invoices_syncable': 0,
        'total_invoices_synced': 0,
        'total_moves_syncable': 0,
        'total_moves_synced': 0,
        'total_syncable': 0,
        'total_synced': 0,
        'pct_synced': 0.0,
    }

    def refresh_dashboard(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        vals = self._compute_totals(cr, uid, ids, None, None, context)
        if vals and ids:
            self.write(cr, uid, ids, vals[ids[0]], context=context)
        return True


BoardDashboardSomsync()
