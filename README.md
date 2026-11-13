# som_sync

An OpenERP module to syncronize OpenERP with Odoo

[![SOM_MODULES](https://github.com/Som-Energia/som_sync_openerp_modules/actions/workflows/som_sync_openerp.yml/badge.svg)](https://github.com/Som-Energia/openerp_som_addons/actions/workflows/som_sync_openerp.yml) [![codecov](https://codecov.io/github/Som-Energia/som_sync_openerp_modules/graph/badge.svg?token=VO8F4EIY8K)](https://codecov.io/github/Som-Energia/som_sync_openerp_modules) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=Som-Energia_som_sync_openerp_modules&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=Som-Energia_som_sync_openerp_modules)

## How to use

Add Odoo connection params in res.config of OpenERP

```
odoo_url_api
odoo_api_key
```

## What it does

*  This OpenERP module override methods create, write, unlink of modules ResPartner, AccountAccount, AccountJournal, AccountMove and AccountMoveLine.
*  Encueue whatever action it does, in a queue to update to Odoo asyncronious.
*  The worker try to create, write or unlink the object in Odoo.


## Group 5 accounts

ERP accounts whose `code` starts with `5` are always excluded from remote account
synchronization. This is a fixed rule, independent of `odoo_account_code` and
configuration. Any legacy `odoo_sync_excluded_account_groups` setting is ignored;
existing stored values are not deleted.

Creating an excluded account does not start synchronization. Manual and
dependency synchronization never look it up remotely, create or update it in
Odoo, or create an `odoo.sync` mapping. Configure the account and its local
`odoo.sync` mapping manually before synchronizing objects that reference it.
A missing mapping produces an error on the dependent object's synchronization,
not on account creation. Existing ERP account validation still applies.

## Duplicating accounts safely

For accounts with a 12-character code or an explicit `odoo_account_code`, use
**Actions → Duplicate account...** instead of the standard Duplicate command.
Enter the final account code and confirm the Odoo mapping before creating the
account. Neither code is prefilled from the source. A 12-character account code
requires an Odoo code of exactly 9 digits, as with normal account creation.

The wizard uses the standard `copy()` chain, preserving configuration, child
account and consolidation behavior, translations, and installed copy extensions.
If child accounts are included by the standard copy, enter their final codes
and mappings in the child table too. Each account uses its own confirmed values;
children do not inherit the new parent's mapping or name. All code confirmations
are checked before copying starts.

Canceling creates no account and starts no synchronization. The source accounts
and their Odoo links remain unchanged. Accounts without a mapping and with a code
length other than 12 retain their standard duplication behavior. During copying,
the confirmed codes are applied before `create()`, not corrected afterwards.

## Odoo API doc
The API documentation is here https://som-energia.github.io/odoo_api_doc/index_swagger.html

## Sync profiles (review foundation)

`odoo.sync` now scopes identities and diagnostics by `sync_profile`: `all_in`
retains the original circuit, `only_moves` identifies the proposed journal-entry
destination, and `shared` is reserved for account mappings outside ERP group 5.
Group 5 accounts use separate mappings per profile. Both runtime classification
and the initial migration use the fixed ERP `code` prefix `5`, not
`odoo_account_code`. The migration preserves IDs and states, shares other account
mappings and leaves group 5 on `all_in`.

Once an account has any saved mapping (in any profile or state, even without an
Odoo ID), code changes that cross the shared/per-profile boundary are blocked.
Changes within the same classification remain allowed. Reclassification requires an explicit
mapping migration; mappings are never moved or merged automatically. Rotating an
API key does not change mapping identities.

The `only_moves` context selects `odoo_api_key_only_moves` on the same configured
Odoo URL. This key is empty by default and never falls back to `odoo_api_key`.
Only moves, move lines, journals, accounts and minimal partners are allowed.
Partner payloads exclude fiscal/payment dependencies before FK resolution;
addresses are not part of this profile. Posted moves follow the ordinary entry
route, including TPV moves, while retaining posted/valid-line checks.

Use **Sync** from an existing `odoo.sync` record to retry its saved profile.
Each selected record gets an independent context. This retries creation/linking;
it does not update an already linked master. PATCH updates and their recovery
are deferred for `only_moves`. Existing PATCH behavior in the original circuit
is preserved. Generic document actions remain on `all_in`.

Attempts to synchronize a model forbidden by its profile are recorded in
`odoo.sync` as errors under the attempted profile, including the rejection reason
and routing flags. Repeated attempts update the same diagnostic record, preserve
any existing Odoo ID, and never schedule or send the rejected operation. These
diagnostics do not authorize mappings or retries for forbidden models. Dry runs
do not create diagnostics.

Manual and scheduled loading require receiver prerequisites to be verified before
activation: company-scoped identities, duplicate-entry protection and the agreed
shared-account behavior. The scheduled-loading function is available, but no cron
is activated automatically; there is no new event routing or Odoo API change. A
common local account mapping does not itself make an Odoo account shared; the
remote account must actually belong to both companies. Account write propagation,
partner event fan-out, production bulk-loading orchestration and accounting lifecycle policy remain
separate work. Pause/drain pre-upgrade jobs before migrating and configure the new
key only when the receiver and profile-specific mappings are ready.

### Manual partner and journal-entry loading with ERPpeek

Use `only_moves_manual_load=True` for an explicit manual load, whether initial
or subsequent. Do not reuse the cron flag or set `from_fk_sync` to enqueue it.
Only run this after the receiver prerequisites above have been verified and
the dedicated API key has been configured.

With `client` connected to the source ERP, define the common manual-load context:

```python
context = {'sync_profile': 'only_moves', 'only_moves_manual_load': True}
```

Choose the appropriate call below. Replace the example IDs with IDs from the
source ERP, **not Odoo IDs**. These are alternatives, not a sequence to run together;
each call performs a real load.

| Operation | ERPpeek call |
|---|---|
| One partner | `client.execute('odoo.sync', 'common_sync_model_create_update', 'res.partner', 'sync', 123, context=context)` |
| Several partners | `client.execute('odoo.sync', 'common_sync_model_create_update', 'res.partner', 'sync', [123, 456], context=context)` |
| One journal entry | `client.execute('odoo.sync', 'common_sync_model_create_update', 'account.move', 'sync', 12345, context=context)` |
| Several journal entries | `client.execute('odoo.sync', 'common_sync_model_create_update', 'account.move', 'sync', [12345, 12346], context=context)` |

An existing `odoo.sync.model.config` for the selected model is required. With
`async_enabled=True`, each record is scheduled separately on `sync_odoo`;
the queue worker must be running. With `async_enabled=False`, loading runs
synchronously. `auto_sync` need not be enabled for an explicit `sync` action.
The manual-load flag does not enable automatic events, forbidden models or
PATCH updates. Already linked partners are not updated.

Journal entries must be posted and have nonempty, valid move lines. Configure the
`only_moves` journal and group-5 account mappings beforehand; other accounts use
`shared` mappings. Partners needed by entries are resolved as dependencies, so a
separate partner load is not required. Zero-amount lines are omitted; an entry
with no remaining nonzero lines produces a local error.

An asynchronous return value of `(None, None)` is not a success receipt. Inspect
the jobs and, after execution, `odoo.sync` records filtered by
`model.model = res.partner` or `account.move`, `res_id` and
`sync_profile = only_moves`. A list call does not return a per-record result summary.

### Scheduled journal-entry loading with `only_moves`

Configure a scheduled action on `account.move`, calling `cron_sync_only_moves`
with a required `date_from` and optional `date_to`, both in `YYYY-MM-DD` format.
The bounds are inclusive and apply to the accounting date, not the creation or
posting timestamp. Omitting `date_to` leaves the upper bound open. For example,
with ERPpeek:

```python
summary = client.execute('account.move', 'cron_sync_only_moves', '2026-11-01')
print(summary)

# Alternative: include an upper accounting-date bound.
summary = client.execute(
    'account.move', 'cron_sync_only_moves', '2026-11-01', '2026-11-30')
print(summary)
```

These are alternative calls; each performs a real load. No scheduled action is
enabled automatically by this feature. Before scheduling, configure the dedicated
key, receiver prerequisites and journal/group-5 mappings described above.

The function scans posted entries in pages of 1,000, skips entries already linked
to an Odoo ID under `only_moves`, and dispatches the rest with
`sync_profile='only_moves'` and `only_moves_cron=True`. The dispatcher requires
nonempty, valid move lines. An existing `odoo.sync.model.config` for `account.move`
is required; `async_enabled` controls queueing and `auto_sync` need not be enabled.
Earlier errors without a remote ID remain candidates on subsequent runs.

ERP server logs at INFO level use the `only_moves cron` prefix: a start message
with the date range, progress for each nonempty page, and a final summary with
elapsed time. These logs are not streamed to the ERPpeek terminal; inspect the
returned dictionary there instead. An illustrative result is:

```python
{
    'sync_profile': 'only_moves',
    'date_from': '2026-11-01',
    'date_to': False,
    'status': 'completed',
    'pages': 2,
    'scanned': 1500,
    'already_linked': 1450,
    'submitted': 50,
    'elapsed_seconds': 1.234,
}
```

| Result field | Meaning |
|---|---|
| `date_to` | Inclusive upper bound, or `False` when omitted (XML-RPC compatible). |
| `status` | `completed`: selection/dispatch finished; `dry_run`: no selection or dispatch; `disabled`: the model has no sync configuration. |
| `pages` | Number of nonempty pages scanned. |
| `scanned` | Posted entries read within the date range, including entries the dispatcher may reject. |
| `already_linked` | Entries skipped because they already have a positive `only_moves` Odoo ID. |
| `submitted` | Unlinked candidates passed to the dispatcher, **not** confirmed queued jobs or successful exports. |
| `elapsed_seconds` | Time spent in this call, including dispatch; excludes subsequent background execution. |

`dry_run` and `disabled` return zero counters. A completed empty range also
returns zero counters. In particular, invalid-line entries can count as
`submitted` even though the dispatcher skips them without scheduling a job.

The scheduler does not inspect queued jobs. At execution time, an `only_moves`
entry job reuses an existing mapping without preparing or sending another entry.
Concurrent POSTs are protected by the receiver's unique `(company_id, pnt_erp_id)`
identity; a duplicate POST may still produce an HTTP 409 diagnostic. This also
requires manual investigation if Odoo accepted an entry but the ERP did not save
its mapping. Inspect jobs and profile-scoped `odoo.sync` diagnostics after each run;
`status='completed'` does not certify that every entry was exported.

## TPV Triodos collections

Individual customer invoice collections in the OpenERP journal `TPV Triodos`
are sent to `bank_statement_lines`, using the journal's existing `odoo.sync`
mapping. Enable automatic, asynchronous `account.move` synchronization and the
journal's **Sync with Odoo Account Moves** flag. The mapped Odoo journal must be
of type `bank` and enabled for ERP synchronization.

After OpenERP reconciles the collection, the worker ensures the invoice is
synchronized and sends one line with `[FACTURA] <invoice number>`. Odoo creates
and reconciles that line without a statement header. The move ID is the retry
identity; these collections are not also exported as generic journal entries.
Valid, reconciled payment lines are supported even when the OpenERP move is
still in `draft`.

Partial, grouped, foreign-currency or ambiguous collections are reported as
sync errors. Moves already exported through `entries` require manual review
before retrying. Inspect `odoo.sync` for the request, endpoint and result.
