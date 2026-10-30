# -*- coding: utf-8 -*-
"""Fase 2: sol·licita la sincronització async dels IDs de la fase 1."""

from __future__ import print_function, unicode_literals

import argparse
import logging
import sys
try:
    from http.client import HTTPException
    from xmlrpc.client import Error
except ImportError:
    from httplib import HTTPException
    from xmlrpclib import Error

from opening_common import is_integer, print_message, read_json, text

logger = logging.getLogger(__name__)

INVOICE = "account.invoice"
SYNC = "odoo.sync"


def load_invoice_ids(path):
    """Valida el manifest complet abans d'enviar cap petició a l'ERP."""
    payload = read_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("metadata"), dict):
        raise ValueError("El manifest ha de contenir metadata i invoice_ids de la fase 1")
    metadata = payload["metadata"]
    if (not is_integer(metadata.get("format_version"))
            or metadata["format_version"] != 1
            or metadata.get("phase") != "identify_invoice_ids"
            or metadata.get("model") != INVOICE):
        raise ValueError("Format, fase o model del manifest no compatible amb la fase 1")
    ids = payload.get("invoice_ids")
    if not isinstance(ids, list) or any(not is_integer(item) or item <= 0 for item in ids):
        raise ValueError("invoice_ids ha de ser una llista d'enters positius")
    if len(ids) != len(set(ids)):
        raise ValueError("El manifest conté IDs de factura duplicats")
    if (not is_integer(metadata.get("invoice_count"))
            or metadata["invoice_count"] != len(ids)):
        raise ValueError("invoice_count no coincideix amb els IDs del manifest")
    return ids


def submit_invoices(client, invoice_ids):
    """Una crida per ID, sense reintents ni consulta dels treballs o resultats."""
    failed_ids = []
    total = len(invoice_ids)
    for position, invoice_id in enumerate(invoice_ids, 1):
        try:
            client.execute(SYNC, "common_sync_model_create_update", INVOICE, "sync", invoice_id)
        except Exception as exc:
            # Una fallada RPC no impedeix intentar els altres IDs del manifest.
            failed_ids.append(invoice_id)
            logger.error("Factura %s: error en la crida RPC: %s", invoice_id, exc)
        if position % 200 == 0 or position == total:
            logger.info("Progrés: %s/%s crides; %s sense error RPC; %s amb error RPC",
                        position, total, position - len(failed_ids), len(failed_ids))
    return failed_ids


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=text,
                        help="Fitxer invoice_ids.json generat en la fase 1")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    try:
        invoice_ids = load_invoice_ids(args.input)
        logger.info("Manifest validat: %s IDs de factura", len(invoice_ids))
        failed_ids = []
        if invoice_ids:
            import dbconfig
            from erppeek import Client

            logger.info("Connectant a l'ERP amb erppeek...")
            client = Client(**dbconfig.erppeek)
            enabled, _, async_enabled = client.execute(
                SYNC, "sync_model_enabled_amplified", INVOICE)
            if not enabled or not async_enabled:
                raise ValueError("account.invoice ha d'estar habilitat per sincronitzar en async")
            logger.info("Sincronització async habilitada; iniciant les crides per factura")
            failed_ids = submit_invoices(client, invoice_ids)
    except (ImportError, KeyError, ValueError, IOError, OSError, Error, HTTPException) as exc:
        print_message("No s'ha pogut completar la fase 2: {}".format(exc), file=sys.stderr)
        return 1
    print_message("Fase 2: {} IDs; {} crides sense error RPC; {} crides amb error RPC".format(
        len(invoice_ids), len(invoice_ids) - len(failed_ids), len(failed_ids)))
    if failed_ids:
        print_message("IDs amb error RPC: {}".format(
            ", ".join(str(invoice_id) for invoice_id in failed_ids)), file=sys.stderr)
    print_message("Crides completades no implica encuaments confirmats. "
                  "Comproveu els resultats amb els logs, odoo.sync i RQ.")
    return 1 if failed_ids else 0


if __name__ == "__main__":
    raise SystemExit(main())
