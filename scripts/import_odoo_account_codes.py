# -*- coding: utf-8 -*-
"""Load the explicit Odoo account-code mapping into OpenERP.

The input file must be UTF-8, semicolon separated and contain every current
OpenERP account exactly once. Its columns are ``old_code;odoo_account_code``.

Example:
    python scripts/import_odoo_account_codes.py --input /tmp/accounts.csv
    python scripts/import_odoo_account_codes.py --input /tmp/accounts.csv --apply
    python scripts/import_odoo_account_codes.py --input /tmp/accounts.csv --apply --finalize
"""
from __future__ import print_function, unicode_literals

import argparse
import io
import re
import sys

import dbconfig


ODOO_ACCOUNT_CODE_RE = re.compile(r'^\d{9}$')


def read_mappings(path):
    mappings = {}
    with io.open(path, 'r', encoding='utf-8') as mapping_file:
        for line_number, line in enumerate(mapping_file, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            columns = [value.strip() for value in line.split(';')]
            if line_number == 1 and columns == ['old_code', 'odoo_account_code']:
                continue
            if len(columns) != 2 or not all(columns):
                raise ValueError(
                    'Line {} must contain old_code;odoo_account_code'.format(
                        line_number
                    )
                )
            old_code, odoo_account_code = columns
            if old_code in mappings:
                raise ValueError('Duplicated OpenERP account code: {}'.format(old_code))
            if not ODOO_ACCOUNT_CODE_RE.match(odoo_account_code):
                raise ValueError(
                    'Invalid Odoo account code on line {}: {}'.format(
                        line_number, odoo_account_code
                    )
                )
            mappings[old_code] = odoo_account_code
    if not mappings:
        raise ValueError('The mapping file is empty')
    return mappings


def get_accounts(client):
    account_ids = client.AccountAccount.search([], order='code asc, id asc')
    return client.AccountAccount.read(
        account_ids, ['id', 'code', 'name', 'odoo_account_code']
    )


def validate_mappings(accounts, mappings):
    accounts_by_code = {}
    for account in accounts:
        accounts_by_code.setdefault(account['code'], []).append(account)

    unknown_codes = sorted(set(mappings) - set(accounts_by_code))
    if unknown_codes:
        raise ValueError(
            'OpenERP account codes not found: {}'.format(', '.join(unknown_codes))
        )

    ambiguous_codes = sorted(
        code for code, matches in accounts_by_code.items() if len(matches) != 1
    )
    if ambiguous_codes:
        raise ValueError(
            'OpenERP account codes are not unique: {}'.format(
                ', '.join(ambiguous_codes)
            )
        )

    missing_codes = sorted(set(accounts_by_code) - set(mappings))
    if missing_codes:
        raise ValueError(
            'Accounts without a mapping: {}'.format(', '.join(missing_codes))
        )

    mapped_codes = list(mappings.values())
    duplicate_odoo_codes = sorted(
        code for code in set(mapped_codes) if mapped_codes.count(code) > 1
    )
    if duplicate_odoo_codes:
        raise ValueError(
            'Odoo account codes are duplicated: {}'.format(
                ', '.join(duplicate_odoo_codes)
            )
        )

    return [
        (accounts_by_code[old_code][0]['id'], odoo_account_code)
        for old_code, odoo_account_code in mappings.items()
    ]


def apply_mappings(client, updates):
    for account_id, odoo_account_code in updates:
        client.AccountAccount.write(
            [account_id], {'odoo_account_code': odoo_account_code}
        )


def finalize_database():
    try:
        import psycopg2
    except ImportError:
        raise RuntimeError('psycopg2 is required to finalize the database schema')

    connection = psycopg2.connect(**dbconfig.psycopg)
    try:
        cursor = connection.cursor()
        cursor.execute(
            'SELECT count(*) FROM account_account '
            'WHERE odoo_account_code IS NULL'
        )
        missing_count = cursor.fetchone()[0]
        if missing_count:
            raise RuntimeError(
                'Cannot finalize: {} accounts have no Odoo account code'.format(
                    missing_count
                )
            )
        cursor.execute(
            'ALTER TABLE account_account '
            'ALTER COLUMN odoo_account_code SET NOT NULL'
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_arguments(arguments):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='Mapping CSV file')
    parser.add_argument(
        '--apply', action='store_true',
        help='Write mappings to OpenERP; omitted means validation only.'
    )
    parser.add_argument(
        '--finalize', action='store_true',
        help='Set odoo_account_code to NOT NULL after applying the mapping.'
    )
    args = parser.parse_args(arguments)
    if args.finalize and not args.apply:
        parser.error('--finalize requires --apply')
    return args


def main(arguments=None):
    args = parse_arguments(arguments)
    mappings = read_mappings(args.input)
    try:
        from erppeek import Client
    except ImportError:
        raise RuntimeError('erppeek is required to load account mappings')
    client = Client(**dbconfig.erppeek)
    updates = validate_mappings(get_accounts(client), mappings)
    print('Validated {} account mappings'.format(len(updates)))
    if not args.apply:
        return 0

    apply_mappings(client, updates)
    print('Applied {} account mappings'.format(len(updates)))
    if args.finalize:
        finalize_database()
        print('Finalized odoo_account_code as required in the database')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('ERROR: {}'.format(error), file=sys.stderr)
        sys.exit(1)
