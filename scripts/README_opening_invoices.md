# Traspàs de factures: simple i per fases

Pla acordat: [issue #77](https://github.com/Som-Energia/som_sync_openerp_modules/issues/77).

1. **Identificar IDs i revisar el control de factures**: implementat en aquest script.
2. **Sincronitzar els IDs** amb `O.OdooSync.common_sync_model_create_update('account.invoice', 'sync', id)`:
   el futur `opening_02_sync_invoices.py` està pendent d'implementar.
3. **Tractar les liquidacions parcials prèvies i els fraccionaments**, incloses
   les factures originals addicionals necessàries; després quadrar el pendent.
4. **Provar la integració dels esdeveniments posteriors** generats a l'ERP:
   remeses, cobraments, devolucions i seqüències completes.

## Fase 1 — Identificar les factures

`scripts/opening_01_export_invoices.py` consulta únicament `account.journal` i
capçaleres d'`account.invoice`. Usa `erppeek` i `Client(**dbconfig.erppeek)` com
els altres scripts. No modifica dades de l'ERP ni d'Odoo.

La selecció exigeix empresa indicada, estat `open`, `residual != 0`, tipus dins
de l'abast i diari amb **`som_sync_odoo_invoices = True`**. Els diaris es consulten
una sola vegada i les factures es filtren amb `journal_id in [...]`, evitant els
dominis relacionats que poden provocar cerques massives en l'ORM antic.

L'abast és explícit:

- `--invoice-scope customers`: `out_invoice` i `out_refund`, per al primer assaig.
- `--invoice-scope suppliers`: `in_invoice` i `in_refund`.
- `--invoice-scope all`: tots quatre tipus; és el valor per defecte.

Les factures parcialment liquidades amb pendent s'inclouen. Les originals pagades
o amb residual zero vinculades a fraccionaments es buscaran en la **fase 3**.
La fase 1 no consulta acords, quotes, apunts, comptes comptables ni `payment_ids`.

## Preparació i execució

Configura `scripts/dbconfig.py`, diccionari `erppeek`, amb `server`, `db`, `user`
i `password` de la còpia ERP de proves. Cal tenir `erppeek` instal·lat i utilitzar
Python 3.7 o superior. La sintaxi respecta els hooks Python 2.7 del repositori,
però l'execució de l'script requereix Python 3.

Treballa sobre una còpia consistent sense moviments durant les consultes i
conserva-la per comparar. Les consultes RPC no comparteixen una transacció comuna.
S'obté el **pendent actual**, no una reconstrucció històrica. `--reference-date`
identifica l'assaig i no filtra registres ni recalcula imports; `--cutoff` es
manté com a àlies compatible. Les dates de les factures no bloquegen l'extracció.

Des de l'arrel del repositori, amb el directori pare de sortida ja existent:

```bash
python3 scripts/opening_01_export_invoices.py \
  --cutoff 2026-10-15 \
  --company-id 1 \
  --invoice-scope customers \
  --snapshot-reference copia-erp-2026-10-15 \
  --output /tmp/ids-clients-2026-10-15
```

El directori de sortida ha de ser **nou**. Els fitxers de les extraccions anteriors
es conserven; no se sobreescriuen. Per a l'arrencada definitiva, la referència
serà `2026-12-31` i l'execució es farà quan s'hagen acabat els moviments.
Es pot ajustar `--batch-size` (200 per defecte). Amb `pyenv`, substitueix
`python3` per `PYENV_VERSION=3.10.20 python` si cal seleccionar l'intèrpret.

Els logs en català mostren connexió, abast, cerques, cada lot de capçaleres,
recomptes, totals de control i fitxers generats. Van a `stderr` amb hora i nivell
`INFO` i es mostren immediatament. No mostren contrasenyes ni payloads complets.

## Resultats: dos fitxers

### `invoice_ids.json`

És el manifest d'IDs per a la futura fase 2, no un payload de factura d'Odoo.
Conté:

- `invoice_ids`: IDs ERP únics i ordenats d'`account.invoice`.
- `metadata`: versió del format, fase `identify_invoice_ids`, model, recompte,
  base de dades d'origen, empresa, abast, diaris habilitats, criteris de selecció,
  identificador de còpia i hores reals d'inici i final de l'extracció.
- `control_totals`: recompte, total original i residual per tipus i moneda,
  calculats amb `Decimal` i guardats com a text.
- `diagnostics`: dates de factura absents que cal revisar; no impedeixen identificar l'ID.

`metadata.residual_basis` és `current_erp_state`. `reference_date` i el camp
compatible `cutoff` són la mateixa referència d'assaig, no un saldo històric.
Les dades completes de factures es llegiran a l'ERP quan se sincronitzen en la
fase 2; no es dupliquen en aquest JSON.

### `invoices.csv`

Una fila per ID, amb les columnes `erp_invoice_id`, `number`, `type`, `state`,
`partner_id`, `currency_id`, `journal_id`, `date_invoice`, `date_due`,
`original_total` i `invoice_residual`. El format és UTF-8 amb separador `;` i
escapat CSV per conservar accents, separadors i salts de línia.
La capçalera és estable també quan no s'ha seleccionat cap factura.

El nou format de fase 1 substitueix el JSON comptable detallat i el checksum del
prototip anterior. Només es generen `invoice_ids.json` i `invoices.csv`.

## Comprovar la selecció

`scripts/opening_01.sql` conté la consulta equivalent per a `--company-id 1`
i `--invoice-scope customers`. Si canvies aquests paràmetres, adapta els filtres
`company_id` i `type` de la SQL. No aplica filtres de data ni les regles de
permisos de l'ORM.

La consulta SQL facilitada per al primer assaig de clients en diaris habilitats
retornava 44.747 factures i 270 rectificatives: **45.017 registres de referència**.
El recompte pot variar segons la còpia i els permisos de l'usuari ERP.

Contrasta els IDs, recomptes i imports amb la mateixa còpia de l'ERP. Els totals
es mantenen separats per tipus i moneda, respectant els signes. L'script rebutja
imports invàlids, lectures incompletes o duplicades i registres que ja no
compleixen la selecció quan es llegeixen.

El pendent d'Odoo es quadrarà **després de la fase 3**: la sincronització existent
crea la factura pel total original. Una factura de 100 amb 40 ja cobrats es
sincronitza inicialment pel total de 100; les liquidacions prèvies han de deixar
el pendent de 60. Una crida asíncrona programada tampoc confirma la creació:
la fase 2 haurà de comprovar els resultats a `odoo.sync`.

## Proves locals

```bash
PYENV_VERSION=3.10.20 python -m unittest discover -s scripts/tests -v
```
