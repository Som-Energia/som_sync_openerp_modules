# -*- coding: utf-8 -*-
"""
Compara les línies d'una remesa ERP amb el payload d'Odoo i extreu les discrepàncies.

    python scripts/export_payment_order_lines_json.py \
      --payment-order-id 14294 \
      --odoo-payload /home/user/remesa_2026_0628 \
      --regenerate-payload
"""
from __future__ import print_function, unicode_literals

import io
import json
import sys
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation

try:
    import argparse
except ImportError:
    argparse = None

import dbconfig
from erppeek import Client


def many2one_id(value):
    if isinstance(value, (list, tuple)) and value:
        return value[0]
    return value if isinstance(value, int) else None


def export_lines(payment_order_id, sync_model_id=134):
    client = Client(**dbconfig.erppeek)
    payment_line_ids = client.execute(
        'payment.line', 'search', [('order_id', '=', payment_order_id)], 0, False, 'id asc')
    if not payment_line_ids or not len(payment_line_ids):
        raise RuntimeError(
            'No hi ha payment.line per a la payment.order {} a {}'.format(
                payment_order_id, dbconfig.erppeek['server']))

    payment_lines = client.execute(
        'payment.line', 'read', payment_line_ids, ['id', 'ml_inv_ref', 'amount'])
    if not payment_lines:
        raise RuntimeError(
            'No s han pogut llegir les payment.line de {}'.format(payment_order_id))

    missing_invoice_lines = [
        line['id'] for line in payment_lines if not many2one_id(line.get('ml_inv_ref'))
    ]
    if missing_invoice_lines:
        raise RuntimeError(
            'Linies de remesa sense ml_inv_ref: {}'.format(missing_invoice_lines))

    erp_invoice_ids = [many2one_id(line['ml_inv_ref']) for line in payment_lines]
    sync_ids = client.execute('odoo.sync', 'search', [
        ('model', '=', sync_model_id),
        ('res_id', 'in', erp_invoice_ids),
    ])
    sync_records = []
    if sync_ids:
        sync_records = client.execute('odoo.sync', 'read', sync_ids, ['res_id', 'odoo_id'])
    odoo_invoice_ids = {
        record['res_id']: record['odoo_id']
        for record in sync_records if record.get('odoo_id')
    }

    missing_sync_invoices = sorted(set(erp_invoice_ids) - set(odoo_invoice_ids))
    if missing_sync_invoices:
        raise RuntimeError(
            'Factures ERP sense mapatge odoo.sync (model {}): {}'.format(
                sync_model_id, missing_sync_invoices))

    return [
        {
            'invoice_id': odoo_invoice_ids[many2one_id(line['ml_inv_ref'])],
            'amount': abs(line.get('amount') or 0.0),
        }
        for line in payment_lines
    ]


def decimal_amount(value, source, line_number):
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise RuntimeError(
            'Import invalid a {} linia {}: {}'.format(source, line_number, value))


def normalize_lines(lines, source):
    normalized_lines = []
    for line_number, line in enumerate(lines, 1):
        if not isinstance(line, dict) or not line.get('invoice_id'):
            raise RuntimeError(
                'invoice_id absent a {} linia {}'.format(source, line_number))
        if 'amount' not in line:
            raise RuntimeError('amount absent a {} linia {}'.format(source, line_number))
        normalized_lines.append({
            'invoice_id': line['invoice_id'],
            'amount': decimal_amount(line['amount'], source, line_number),
        })
    return normalized_lines


def load_payload_lines(payload_path):
    with io.open(payload_path, 'r', encoding='utf-8') as payload_file:
        payload = json.load(payload_file)
    if not isinstance(payload, dict) or not isinstance(payload.get('lines'), list):
        raise RuntimeError('El payload Odoo no conte una llista lines')
    return payload, normalize_lines(payload['lines'], 'payload Odoo')


def regenerate_payload(payment_order_id):
    client = Client(**dbconfig.erppeek)
    payload = client.execute(
        'odoo.sync', 'get_model_vals_to_sync', 'payment.order', payment_order_id)
    if not isinstance(payload, dict) or not isinstance(payload.get('lines'), list):
        raise RuntimeError('El payload regenerat no conte una llista lines')
    return payload, normalize_lines(payload['lines'], 'payload ERP regenerat')


def amounts_by_invoice(lines):
    amounts = defaultdict(Counter)
    for line in lines:
        amounts[line['invoice_id']][line['amount']] += 1
    return amounts


def format_amounts(amounts):
    return ', '.join(
        '{} x {}'.format(count, amount)
        for amount, count in sorted(amounts.items())
    )


def invoice_total(amounts, invoice_ids):
    return sum((
        amount * count
        for invoice_id in invoice_ids
        for amount, count in amounts[invoice_id].items()
    ), Decimal('0'))


def print_comparison(left_lines, left_payload, left_name, odoo_payload, odoo_lines):
    erp_amounts = amounts_by_invoice(left_lines)
    odoo_amounts = amounts_by_invoice(odoo_lines)
    erp_total = sum((line['amount'] for line in left_lines), Decimal('0'))
    odoo_total = sum((line['amount'] for line in odoo_lines), Decimal('0'))
    only_erp = sorted(set(erp_amounts) - set(odoo_amounts))
    only_odoo = sorted(set(odoo_amounts) - set(erp_amounts))
    different_amounts = sorted(
        invoice_id for invoice_id in set(erp_amounts) & set(odoo_amounts)
        if erp_amounts[invoice_id] != odoo_amounts[invoice_id]
    )

    print('Comparativa de linies de remesa')
    print('{}: {} linies, total {}'.format(left_name, len(left_lines), erp_total))
    print('Payload Odoo: {} linies, total {}'.format(len(odoo_lines), odoo_total))
    print('Diferencia {} - Odoo: {}'.format(left_name, erp_total - odoo_total))
    if 'amount' in left_payload:
        print('Total declarat a {}: {}'.format(left_name, left_payload['amount']))
    if 'amount' in odoo_payload:
        print('Total declarat al payload Odoo: {}'.format(odoo_payload['amount']))

    if only_erp:
        print('\nFactures nomes a {} ({}), total {}:'.format(
            left_name, len(only_erp), invoice_total(erp_amounts, only_erp)))
        for invoice_id in only_erp:
            print('  {}: {}'.format(invoice_id, format_amounts(erp_amounts[invoice_id])))

    if only_odoo:
        print('\nFactures nomes al payload Odoo ({}), total {}:'.format(
            len(only_odoo), invoice_total(odoo_amounts, only_odoo)))
        for invoice_id in only_odoo:
            print('  {}: {}'.format(invoice_id, format_amounts(odoo_amounts[invoice_id])))

    if different_amounts:
        erp_difference_total = invoice_total(erp_amounts, different_amounts)
        odoo_difference_total = invoice_total(odoo_amounts, different_amounts)
        print('\nFactures amb imports diferents ({}), {} - Odoo: {}'.format(
            len(different_amounts), left_name, erp_difference_total - odoo_difference_total))
        for invoice_id in different_amounts:
            print('  {}: {} [{}] | Odoo [{}]'.format(
                invoice_id,
                left_name,
                format_amounts(erp_amounts[invoice_id]),
                format_amounts(odoo_amounts[invoice_id]),
            ))

    if not (only_erp or only_odoo or different_amounts):
        print('\nNo hi ha diferencies en les linies.')


def parse_args(argv):
    if argparse is None:
        raise RuntimeError('argparse no disponible')

    parser = argparse.ArgumentParser(
        description='Exporta payment.line al format lines del payload d Odoo')
    parser.add_argument('--payment-order-id', type=int, required=True,
                        help='ID ERP de payment.order, per exemple 14294')
    parser.add_argument('--sync-model-id', type=int, default=134,
                        help='ID d ir.model per account.invoice a odoo.sync (per defecte: 134)')
    parser.add_argument('--output', help='Fitxer JSON de sortida (per defecte: stdout)')
    parser.add_argument('--odoo-payload',
                        help='Fitxer JSON del payload Odoo per comparar les linies')
    parser.add_argument('--regenerate-payload', action='store_true',
                        help='Regenera el payload actual amb get_model_vals_to_sync')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.regenerate_payload and not args.odoo_payload:
        raise RuntimeError('--regenerate-payload requereix --odoo-payload')

    lines = export_lines(args.payment_order_id, args.sync_model_id)

    if args.output:
        with io.open(args.output, 'w', encoding='utf-8') as output_file:
            json.dump(lines, output_file, ensure_ascii=False, indent=2)
            output_file.write(u'\n')
    elif not args.odoo_payload:
        json.dump(lines, sys.stdout, ensure_ascii=False, indent=2)
        print()

    if args.odoo_payload:
        odoo_payload, odoo_lines = load_payload_lines(args.odoo_payload)
        erp_lines = normalize_lines(lines, 'ERP')
        print_comparison(
            erp_lines, {}, 'Linies ERP actuals', odoo_payload, odoo_lines)
        if args.regenerate_payload:
            regenerated_payload, regenerated_lines = regenerate_payload(args.payment_order_id)
            print('\n')
            print_comparison(
                regenerated_lines,
                regenerated_payload,
                'Payload ERP regenerat',
                odoo_payload,
                odoo_lines,
            )


if __name__ == '__main__':
    main()
