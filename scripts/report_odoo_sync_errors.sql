-- Resum de sincronitzacions problemàtiques d'Odoo.
--
-- Canvieu la data de la CTE "params" abans d'executar la consulta.
-- Exemples d'execució:
--   psql -d somenergia -f scripts/report_odoo_sync_errors.sql
--   psql -h localhost -p 5433 -U erp -d somenergia \
--     -f scripts/report_odoo_sync_errors.sql

WITH params AS (
    SELECT TIMESTAMP '2026-09-01 00:00:00' AS date_from
), sincronitzacions AS (
    SELECT
        im.model,
        os.sync_state,
        os.odoo_last_sync_at,
        COALESCE(
            substring(
                os.odoo_last_update_result
                FROM '"msg"[[:space:]]*:[[:space:]]*"([^"\\]*)"'
            ),
            substring(
                os.odoo_last_update_result
                FROM '"message"[[:space:]]*:[[:space:]]*"([^"\\]*)"'
            ),
            NULLIF(btrim(os.odoo_last_update_result), ''),
            '(sense resultat)'
        ) AS error_message
    FROM odoo_sync AS os
    JOIN ir_model AS im ON im.id = os.model
    CROSS JOIN params
    WHERE os.odoo_last_sync_at >= params.date_from
      AND os.sync_state IN ('error', 'draft', 'pending')
)
SELECT
    model,
    regexp_replace(error_message, '[0-9]+', '<id>', 'g') AS tipus_error,
    sync_state AS synchronization_state,
    COUNT(*) AS total,
    MAX(odoo_last_sync_at) AS ultima_sincronitzacio
FROM sincronitzacions
GROUP BY
    model,
    regexp_replace(error_message, '[0-9]+', '<id>', 'g'),
    sync_state
ORDER BY
    total DESC,
    model,
    synchronization_state;
