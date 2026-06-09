# som_sync_openerp - Agent Handbook

## Propositi

Modul de sincronitzacio **unidireccional** (OpenERP 6.1 -> Odoo) via REST API.
Sincronitza factures, asseguts comptables, partners, pagaments, i altres entitats.

## Arquitectura

```
OpenERP 6.1 (osv.osv)                    Odoo (REST API)
+---------------------+                  +---------------------+
| account.invoice     |--POST/PATCH-->   | invoice             |
| account.move        |--POST-------->   | entry               |
| res.partner         |--POST/PATCH-->   | partner             |
| payment.order       |--POST-------->   | payment_orders      |
| ...                 |                  | ...                 |
+---------------------+                  +---------------------+
         |
         v
+---------------------+
| odoo.sync            |  <- Taule de tracking universal
| (model, res_id,      |    (model FK + res_id integer)
|  odoo_id,            |
|  sync_state,         |
|  odoo_last_sync_at)  |
+---------------------+
```

## Taule Central: `odoo.sync`

Cada registre sincronitzat te UNA fila aqui. Constraints: `unique(model, res_id)`.

### Estats (`sync_state`)

| Estat | Significat |
|---|---|
| `draft` | Creat pero no sincronitzat |
| `pending` | Esperant processament (payment.order) |
| `synced` | Sincronitzat correctament |
| `synced_with_warning` | Sincronitzat amb discrepancies (ex: imports) |
| `error` | Error en la sincronitzacio |
| `static` | Model estatic (tax, journal, etc.) - sense registre real |

## Configuracio de Sincronitzacio

### Per journal (`account.journal`)

- `som_sync_odoo_invoices` (boolean) - Habilita sync de factures d'aquest journal
- `som_sync_odoo_account_moves` (boolean) - Habilita sync d'asseguts d'aquest journal

### Per model (`odoo.sync.model.config`)

- `model_id` -> `ir.model`
- `auto_sync` - Sync automatic al create/write/unlink
- `async_enabled` - Utilitzar job queue (oorq)

### Per mode de pagament (`payment.mode`)

- `som_sync_odoo` (boolean) - Habilita sync d'ordres de pagament

### Config global (`res.config`)

- `odoo_url_api` - URL base de l'API Odoo
- `odoo_api_key` - Clau API

## Restriccions per Model

| Model | Restriccions per sincronitzar |
|---|---|
| `account.invoice` | `journal.som_sync_odoo_invoices = True` AND `state IN ('open','paid')` |
| `account.move` | `journal.som_sync_odoo_account_moves = True` |
| `payment.order` | `state = 'done'` AND `mode.som_sync_odoo = True` |
| `res.partner` / `res.partner.address` | Sempre sincronitzable |
| `account.account` | Sempre sincronitzable |
| Models estatics | Sempre sincronitzables (noms map IDs) |

## Flux de Sincronitzacio

```
write() / create() al model ERP
  |
  v
check_special_restrictions()  <- Restriccions especifices del model
  |
  v
sync_model_enabled_amplified()  <- odoo.sync.model.config
  |
  |-- auto_sync=False -> SKIP (excepte wizard on-demand)
  |
  v
syncronize_sync() / syncronize() (async)
  |
  |-- Models estatics -> get_or_create_static_odoo_id()
  |-- FK sync -> get_odoo_id_by_erp_id() (lookup local)
  -- Full sync -> GET/POST/PATCH API
         |
         v
      update_odoo_id() -> persisteix a odoo.sync (finally block)
```

## Models Sincronitzables

| Model | Endpoint POST | Endpoint GET | FK Sync |
|---|---|---|---|
| `account.account` | `accounts` | `code` | -- |
| `account.invoice` | `invoices` | -- | partner, journal, payment_term, payment_type, fiscal_position |
| `account.move` | `entries` | -- | journal |
| `res.partner` | `partners` | `vat` | account, fiscal_position, payment_term, payment_type |
| `res.partner.address` | `partners` | `contact/{id}/invoice` | state, country, partner |
| `res.partner.bank` | `banks` | `partner_odoo_id?iban=` | partner |
| `payment.order` | `payment_orders` | -- | -- |
| `giscedata.facturacio.devolucio` | `payment_order_refunds` | -- | account, journal |

## Models Estatics (sense registre real)

`account.fiscal.position`, `account.journal`, `account.payment.term`, `account.tax`, `payment.type`, `res.country`

## Estructura de Fitxers

```
models/
  odoo_sync.py              # Model central odoo.sync (940 linies)
  odoo_sync_model_config.py # Config per model
  account_invoice.py        # Sync factures + check_special_restrictions
  account_move.py           # Sync asseguts
  account_journal.py        # Camps som_sync_odoo_*
  res_partner.py            # Sync partners (+ PATCH bidireccional)
  payment_order.py          # Sync ordres pagament (complex: grouped/refund/splitted)
  # (sense model Python per dashboard - les queries SQL son als custom.search records)
  ...
views/
  odoo_sync_view.xml        # Form/tree odoo.sync + accions
  board_dashboard_somsync_view.xml # Dashboard
  ...
wizard/
  wizard_sync_object_odoo.py       # Sync on-demand
  wizard_open_related_model_record.py  # Obrir registre ERP
  wizard_open_related_odoo_record.py   # Obrir URL Odoo
```

## Com Afegir un Nou Model Sincronitzable

1. Crear fitxer `models/nou_model.py` amb classe que hereta del model
2. Definir `MAPPING_FIELDS_TO_SYNC`, `MAPPING_FK`, `get_endpoint_suffix`
3. Implementar `check_special_restrictions()` si cal
4. Afegir a `models/__init__.py`
5. Afegir mappings a `odoo_sync.py` (`MAPPING_MODELS_POST`, `MAPPING_MODELS_GET`, etc.)
6. Afegir dades a `data/som_sync_openerp_data.xml` (`odoo.sync.model.config`)
7. Afegir accio `act_window` a `views/odoo_sync_view.xml`

## Gotchas

- **Python 2**: `from __future__ import absolute_import` a tots els fitxers
- **osv.osv**: No es `models.Model` - herencia amb `_inherit`, camps amb `fields.*`
- **Sudo**: `from service.security import Sudo` + `with Sudo(uid=1, gid=0):`
- **oorq**: Jobs asincrons amb `@job(queue='default')` decorator
- **PATCH**: Noms `res.partner` i `res.partner.address` tenen actualitzacio bidireccional
- **Discrepacies imports**: `synced_with_warning` amb tolerancia configurable (`odoo_sync_invoice_amount_tolerance`, default 0.02EUR)

## Dashboard

El dashboard utilitza el patro `custom.search` + `custom.search.results` + `board.board`:

- **4 custom.search records**: cadascun amb una query SQL que retorna una fila (name, value) per metrica
- **4 act_window actions**: `res_model='custom.search.results'` amb `context[b'search_id']` apuntant al custom.search
- **4 board.board.line**: un per metrica al board.board
- **Filtre per data**: 01/01/2026 (fixe a les queries SQL)
- **Optimitzacio**: COUNT(*) + INNER JOIN. Les "synced" fan INNER JOIN amb odoo.sync
- **Dependencia**: moduls `board` i `custom_search`

### Patro custom.search

1. `custom.search` conté la query SQL (campo `query`)
2. `custom.search.results` executa la query via `read()` i genera vistes dinàmiques via `fields_view_get()`
3. `ir.actions.act_window` enllaça `custom.search.results` amb `context[b'search_id']` = ref del custom.search
4. `board.board.line` mostra l'acció al dashboard

### Rendiment

Amb 40M+ factures i 100M+ assentaments:
- Les queries de "syncable" fan un sol scan amb COUNT(*)
- Les queries de "synced" fan INNER JOIN (no LEFT JOIN) amb odoo.sync, reduint el treball
- Cada query retorna 1 fila, no 140M+

### Refresh

Les dades es recalculen cada cop que es carrega el dashboard (executa la query SQL en temps real).
No cal reinstal·lar el modul.
