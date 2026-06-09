#  -*- coding: utf-8 -*-
from osv import osv, fields

# SQL view that joins sync tracking with invoice/move data
# to allow filtering by date on the dashboard
SYNC_SUMMARY_VIEW = """
CREATE OR REPLACE VIEW board_dashboard_somsync_summary AS
    SELECT
        row_number() OVER () AS id,
        'account.invoice' AS model_name,
        ai.id AS erp_id,
        ai.date_invoice AS date_ref,
        COALESCE(os.sync_state, 'not_synced') AS sync_state
    FROM account_invoice ai
    INNER JOIN account_journal aj ON ai.journal_id = aj.id
    LEFT JOIN ir_model im ON im.model = 'account.invoice'
    LEFT JOIN odoo_sync os ON os.model = im.id AND os.res_id = ai.id
    WHERE aj.som_sync_odoo_invoices = True
      AND ai.state IN ('open', 'paid')
      AND ai.date_invoice >= '2026-01-01'

    UNION ALL

    SELECT
        row_number() OVER () + 10000000 AS id,
        'account.move' AS model_name,
        am.id AS erp_id,
        am.date AS date_ref,
        COALESCE(os.sync_state, 'not_synced') AS sync_state
    FROM account_move am
    INNER JOIN account_journal aj ON am.journal_id = aj.id
    LEFT JOIN ir_model im ON im.model = 'account.move'
    LEFT JOIN odoo_sync os ON os.model = im.id AND os.res_id = am.id
    WHERE aj.som_sync_odoo_account_moves = True
      AND am.date >= '2026-01-01'
"""


class BoardDashboardSomsync(osv.osv):
    _name = 'board.dashboard.somsync.summary'
    _description = 'Dashboard Sincronitzacio - Summary View'
    _auto = False
    _rec_name = 'model_name'

    def init(self, cr):
        cr.execute("DROP VIEW IF EXISTS board_dashboard_somsync_summary")
        cr.execute(SYNC_SUMMARY_VIEW)

    _columns = {
        'model_name': fields.char('Model', size=32),
        'erp_id': fields.integer('ERP ID'),
        'date_ref': fields.date('Data'),
        'sync_state': fields.char('Estat sincronitzacio', size=32),
    }


BoardDashboardSomsync()
