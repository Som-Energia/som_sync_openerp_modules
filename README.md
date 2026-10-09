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


## Odoo API doc
The API documentation is here https://som-energia.github.io/odoo_api_doc/index_swagger.html

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
