// Factures obertes amb residu diferent de zero
SELECT
    ai.id           AS erp_invoice_id,
    ai.number,
    ai.type,
    ai.state,
    ai.partner_id,
    ai.currency_id,
    ai.journal_id,
    ai.date_invoice,
    ai.date_due,
    ai.amount_total AS original_total,
    ai.residual     AS invoice_residual
FROM account_invoice ai
JOIN account_journal aj ON aj.id = ai.journal_id
WHERE ai.company_id = 1
  AND ai.state = 'open'
  AND ai.residual <> 0
  AND ai.type IN ('out_invoice', 'out_refund')
  AND aj.som_sync_odoo_invoices = TRUE
ORDER BY ai.id;


// Factures obertes amb residu diferent de zero agrupades per any
SELECT
    EXTRACT(YEAR FROM ai.date_invoice)::integer AS any_factura,
    COUNT(*) AS total_factures
FROM account_invoice ai
JOIN account_journal aj ON aj.id = ai.journal_id
WHERE ai.company_id = 1
  AND ai.state = 'open'
  AND ai.residual <> 0
  AND ai.type IN ('out_invoice', 'out_refund')
  AND aj.som_sync_odoo_invoices = TRUE
GROUP BY EXTRACT(YEAR FROM ai.date_invoice)
ORDER BY any_factura NULLS LAST;
