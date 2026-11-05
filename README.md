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


## Excluding account groups from synchronization

Set `odoo_sync_excluded_account_groups` in `res.config` to a comma-separated
list of ERP account groups (the first digit of the account code), for example
`2,5`. Exclusions are disabled by default: a missing setting, an empty value,
or `False` excludes no accounts. Upgrade `som_sync_openerp` to
create this configuration entry in an existing ERP installation. It is declared
with `noupdate="1"` so subsequent module upgrades preserve your configured value.

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
destination, and `shared` is reserved for account mappings outside ERP group 5
(account codes starting with `5`). The migration retains existing IDs and states,
shares the other account mappings and leaves group 5 mappings on `all_in`.
Group 5 accounts use separate mappings per profile at runtime too. Rotating an
API key does not change these identities.

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

This is infrastructure for review, **not a deployable moves-only circuit yet**:
there is no moves cron, no new event routing and no changes to the Odoo API.
Do not activate the profile until the receiver has company-scoped identity
lookups, idempotent entry creation and the agreed shared-account behavior. A
common local account mapping does not itself make an Odoo account shared; the
remote account must actually belong to both companies. Account write propagation,
partner event fan-out, production bulk-loading orchestration and accounting lifecycle policy remain
separate work. Pause/drain pre-upgrade jobs before migrating and keep the new
key unset during this first review.

### Manual partner loading with ERPpeek

Use `only_moves_manual_load=True` for an explicit manual load, whether initial
or subsequent. Do not reuse the cron flag or set `from_fk_sync` to enqueue it.
Only run this after the receiver prerequisites above have been verified and
the dedicated API key has been configured.

With `client` connected to the source ERP and `partner_ids` containing the
selected ERP partner IDs:

```python
context = {'sync_profile': 'only_moves', 'only_moves_manual_load': True}
for partner_id in partner_ids:
    client.execute(
        'odoo.sync', 'common_sync_model_create_update',
        'res.partner', 'sync', partner_id, context=context,
    )
```

An existing `odoo.sync.model.config` for `res.partner` is required. With
`async_enabled=True`, each partner is scheduled separately on `sync_odoo`;
the queue worker must be running. With `async_enabled=False`, loading runs
synchronously. `auto_sync` need not be enabled for an explicit `sync` action.
The manual-load flag does not enable automatic events, forbidden models or
PATCH updates. Already linked partners are not updated.

An asynchronous return value of `(None, None)` is not a success receipt. Inspect
the jobs and, after execution, `odoo.sync` records filtered by
`model.model = res.partner`, `res_id` and `sync_profile = only_moves`.

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
