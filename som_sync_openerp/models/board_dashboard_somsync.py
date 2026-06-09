#  -*- coding: utf-8 -*-
from osv import osv, fields

# Pre-aggregated SQL view: returns only summary rows (not 140M+ individual rows).
# The dashboard indicators count rows, so each summary row = one metric.
# Uses conditional aggregation (CASE WHEN) to avoid expensive LEFT JOINs.
SYNC_SUMMARY_VIEW = """
CREATE OR REPLACE VIEW board_dashboard_somsync_summary AS
    SELECT
        1 AS id,
        'account.invoice' AS model_name,
        'syncable' AS metric,
        COUNT(*) AS value
    FROM account_invoice ai
    INNER JOIN account_journal aj ON ai.journal_id = aj.id
    WHERE aj.som_sync_odoo_invoices = True
      AND ai.state IN ('open', 'paid')
      AND ai.date_invoice >= '2026-01-01'

    UNION ALL

    SELECT
        2 AS id,
        'account.invoice' AS model_name,
        'synced' AS metric,
        COUNT(*) AS value
    FROM account_invoice ai
    INNER JOIN account_journal aj ON ai.journal_id = aj.id
    INNER JOIN ir_model im ON im.model = 'account.invoice'
    INNER JOIN odoo_sync os ON os.model = im.id AND os.res_id = ai.id
        AND os.sync_state IN ('synced', 'synced_with_warning')
    WHERE aj.som_sync_odoo_invoices = True
      AND ai.state IN ('open', 'paid')
      AND ai.date_invoice >= '2026-01-01'

    UNION ALL

    SELECT
        3 AS id,
        'account.move' AS model_name,
        'syncable' AS metric,
        COUNT(*) AS value
    FROM account_move am
    INNER JOIN account_journal aj ON am.journal_id = aj.id
    WHERE aj.som_sync_odoo_account_moves = True
      AND am.date >= '2026-01-01'

    UNION ALL

    SELECT
        4 AS id,
        'account.move' AS model_name,
        'synced' AS metric,
        COUNT(*) AS value
    FROM account_move am
    INNER JOIN account_journal aj ON am.journal_id = aj.id
    INNER JOIN ir_model im ON im.model = 'account.move'
    INNER JOIN odoo_sync os ON os.model = im.id AND os.res_id = am.id
        AND os.sync_state IN ('synced', 'synced_with_warning')
    WHERE aj.som_sync_odoo_account_moves = True
      AND am.date >= '2026-01-01'
"""


class BoardDashboardSomsync(osv.osv):
    _name = 'board.dashboard.somsync.summary'
    _description = 'Dashboard Sincronitzacio - Summary'
    _auto = False
    _rec_name = 'model_name'

    def init(self, cr):
        cr.execute("DROP VIEW IF EXISTS board_dashboard_somsync_summary")
        cr.execute(SYNC_SUMMARY_VIEW)

    _columns = {
        'model_name': fields.char('Model', size=32),
        'metric': fields.char('Metrica', size=16),
        'value': fields.integer('Valor'),
    }


BoardDashboardSomsync()
