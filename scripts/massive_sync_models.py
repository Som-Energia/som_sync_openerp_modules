# -*- coding: utf-8 -*-
"""
Script to launch the initial massive sync of ERP master models to Odoo.

This script is intended to be executed directly from IPython, not imported as a module.

It intentionally performs the sync at top level when loaded.

Only non-static models should be included here. Static models such as
account.journal, account.tax or payment.type are resolved through static
odoo.sync mappings loaded from migration CSV files, not through the HTTP
create/update sync flow.

The order of MASTER_MODELS is intentional:
- account.account must be synced before res.partner because partners depend on
  receivable/payable accounts.
- res.partner must be synced before res.partner.bank because bank accounts need
  the partner odoo.sync mapping to build their endpoint suffix.

Each model domain filters out records that cannot build a valid Odoo endpoint
suffix, such as partners without VAT, states without country/REE code, or bank
accounts without IBAN.
"""
import erppeek
from tqdm import tqdm

O = erppeek.Client('http://localhost:1234', 'db', 'user')  # noqa: E741

MASTER_MODELS = [
    {
        'model': 'account.account',
        'domain': [
            ('code', '!=', False),
        ],
    },
    {
        'model': 'res.country.state',
        'domain': [
            ('ree_code', '!=', False),
            ('country_id', '!=', False),
        ],
    },
    {
        'model': 'res.municipi',
        'domain': [
            ('ine', '!=', False),
        ],
    },
    {
        'model': 'res.partner',
        'domain': [
            ('vat', '!=', False),
        ],
    },
    {
        'model': 'res.partner.bank',
        'domain': [
            ('partner_id', '!=', False),
            ('iban', '!=', False),
        ],
    },
]


def sync_model(model_name, domain):
    ids_to_sync = O.model(model_name).search(domain)
    failures = []

    print('Syncing %s records of model %s' % (len(ids_to_sync), model_name))
    for id in tqdm(ids_to_sync):
        try:
            O.OdooSync.common_sync_model_create_update(model_name, 'sync', id)
        except Exception as e:
            failures.append((model_name, id, e))
            print('Failed syncing %s %s: %s' % (model_name, id, e))

    print(
        'Finished %s: %s ok, %s failed' % (
            model_name,
            len(ids_to_sync) - len(failures),
            len(failures),
        )
    )
    return failures


all_failures = []
for master_model in MASTER_MODELS:
    all_failures.extend(sync_model(master_model['model'], master_model['domain']))

if all_failures:
    print('Sync finished with failures:')
    for model_name, id, error in all_failures:
        print('- %s %s: %s' % (model_name, id, error))
else:
    print('Sync finished without failures')
