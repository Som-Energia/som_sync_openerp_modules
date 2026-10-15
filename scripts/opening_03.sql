-- Equivalent a --company-id 1 --invoice-scope customers.
-- Pendent actual: sense filtre de data ni d'estat/residual de la factura original.
-- Una fila per quota; els acords sense quotes també apareixen (LEFT JOIN).
-- Per comptar acords/factures, useu COUNT(DISTINCT aif.id) / COUNT(DISTINCT ai.id).
-- La SQL directa no aplica els permisos de l'ORM.
SELECT
    aif.id                  AS erp_fraccionament_id,
    aif.codi,
    aif.state               AS agreement_state,
    aif.import_a_fraccionar  AS amount_total,
    ai.id                   AS erp_invoice_id,
    ai.number               AS invoice_number,
    ai.type                 AS invoice_type,
    ai.state                AS invoice_state,
    ai.partner_id,
    ai.currency_id,
    ai.journal_id,
    ai.amount_total         AS original_total,
    ai.residual             AS invoice_residual,
    line.id                 AS erp_line_id,
    line.import             AS amount,
    line.state              AS line_state,
    line.data_venciment     AS date_due,
    line.data_aplicacio     AS application_date,
    line.move_line_id,
    line.invoice_desti_id,
    line.remesa_desti_id,
    line.applied_move_id,
    line.applied_move_line_id,
    line.canceled_move_id,
    line.agrupacio_move_id
FROM account_invoice_fraccionament aif
JOIN account_invoice ai ON ai.id = aif.invoice_id
JOIN account_journal aj ON aj.id = ai.journal_id
LEFT JOIN account_invoice_fraccionament_fraccionaments line
    ON line.invoice_fraccionament_id = aif.id
WHERE aif.company_id = 1
  AND aif.state IN ('no_cobrat', 'parcialment_cobrat')
  AND ai.company_id = 1
  AND ai.type IN ('out_invoice', 'out_refund')
  AND aj.som_sync_odoo_invoices = TRUE
ORDER BY aif.id, line.id;
