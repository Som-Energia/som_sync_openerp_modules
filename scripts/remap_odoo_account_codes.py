#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Remap selected ERP accounts from a semicolon-delimited ERP;Odoo CSV.

Supports Python 2.7 and Python 3 using scripts/dbconfig.py and erppeek.
ERP/Odoo validation is read-only unless --apply is supplied. Every run writes
a CSV report beside the input (or at --report). Existing files are never replaced.
Unavailable destinations are reported and skipped, even with --apply. Exit code
2 means the batch completed with skipped accounts; 1 means a fatal error.
Example:
    python scripts/remap_odoo_account_codes.py --input mapeig_261102.csv
    python scripts/remap_odoo_account_codes.py --input mapeig_261102.csv \
        --apply --backup /safe/path/account-remapping-before.json

Before applying, pause concurrent account synchronization and queued account
jobs. account.account synchronization must be enabled and async disabled.
The backup preserves old codes and sync metadata; it is NOT an automatic undo.
Each RPC commits independently: failures can leave a partially applied batch.
The normal synchronizer can create remote accounts after a failed lookup, even
though this script checks every destination first. Review errors before retrying.
Deleting a local mapping does not delete or unlink the old account in Odoo.
"""

from __future__ import print_function, unicode_literals

import argparse
from collections import OrderedDict
import csv
from datetime import datetime
import io
import json
import os
import re
import sys


PY2 = sys.version_info[0] == 2
try:
    integer_types = (int, long)
    text_type = unicode
except NameError:
    integer_types = (int,)
    text_type = str


ACCOUNT = "account.account"
SYNC = "odoo.sync"
CONTEXT = {"active_test": False}
ACCOUNT_FIELDS = ["code", "name", "company_id", "odoo_account_code"]
SYNC_FIELDS = [
    "model", "res_id", "odoo_id", "sync_state", "odoo_last_sync_at",
    "odoo_created_at", "odoo_updated_at", "odoo_last_update_result",
    "odoo_last_sync_request", "odoo_last_sync_endpoint",
]
REPORT_FIELDS = ["ERP", "Odoo", "erp_id", "odoo_id", "status", "message"]


def text(value):
    return value.decode("utf-8") if isinstance(value, bytes) else text_type(value)


def print_message(message, stream=None):
    stream = stream if stream is not None else sys.stdout
    message = text(message) + "\n"
    stream.write(message.encode("utf-8") if PY2 else message)
    stream.flush()


def normalize_code(value, length, line):
    code = re.sub(r"[.,\s]", "", text(value))
    if not re.match(r"\A[0-9]{%s}\Z" % length, code):
        raise ValueError("Invalid {}-digit code on CSV line {}: {!r}".format(
            length, line, value))
    return code


def read_mappings(path):
    mappings = OrderedDict()
    # Python 2's csv module requires bytes; Python 3's requires text.
    source = open(path, "rb") if PY2 else io.open(
        path, encoding="utf-8-sig", newline="")
    with source:
        reader = csv.DictReader(source, delimiter=str(";"))
        headers = [text(field) for field in (reader.fieldnames or [])]
        if headers:
            headers[0] = headers[0].lstrip("\ufeff")
        if headers != ["ERP", "Odoo"]:
            raise ValueError("CSV header must be ERP;Odoo")
        reader.fieldnames = [str("ERP"), str("Odoo")]
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Invalid CSV row on line {}".format(reader.line_num))
            code = normalize_code(row["ERP"], 12, reader.line_num)
            target = normalize_code(row["Odoo"], 9, reader.line_num)
            if code in mappings:
                raise ValueError("Duplicate ERP code: {}".format(code))
            mappings[code] = target
    if not mappings:
        raise ValueError("CSV contains no mappings")
    return mappings


def read_records(client, model, domain, fields):
    ids = client.execute(model, "search", domain, context=dict(CONTEXT))
    if not ids:
        return []
    return client.execute(model, "read", ids, fields, context=dict(CONTEXT))


def read_syncs(client, account_id):
    return read_records(client, SYNC, [
        ("model.model", "=", ACCOUNT), ("res_id", "=", account_id),
    ], SYNC_FIELDS)


class Report(object):
    """Persist a complete CSV snapshot after each account, including on failure."""

    def __init__(self, path):
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        self.stream = (os.fdopen(descriptor, "wb") if PY2 else
                       io.open(descriptor, "w", encoding="utf-8", newline=""))

    def write(self, updates):
        self.stream.seek(0)
        self.stream.truncate()
        writer = csv.writer(self.stream, delimiter=str(";"))

        def row(values):
            values = [text(value) for value in values]
            writer.writerow([value.encode("utf-8") for value in values] if PY2 else values)

        row(REPORT_FIELDS)
        for item in updates:
            row([item["account"]["code"], item["target"], item["account"]["id"],
                 item["odoo_id"] or "", item["status"], item.get("message", "")])
        self.stream.flush()
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def prepare_updates(client, mappings):
    print_message("Checking account synchronization configuration")
    enabled, _, asynchronous = client.execute(
        SYNC, "sync_model_enabled_amplified", ACCOUNT)
    if not enabled or asynchronous:
        raise ValueError("account.account sync must be enabled with async disabled")
    print_message("Reading {} ERP accounts".format(len(mappings)))
    accounts = read_records(
        client, ACCOUNT, [("code", "in", list(mappings))], ACCOUNT_FIELDS)
    by_code = {}
    for account in accounts:
        by_code.setdefault(account["code"], []).append(account)
    for code in mappings:
        if len(by_code.get(code, [])) != 1:
            raise ValueError("Expected exactly one ERP account for {}".format(code))

    destinations = {}
    lookup_errors = {}
    codes = sorted(set(mappings.values()))
    for position, code in enumerate(codes, 1):
        print_message("[Odoo {}/{}] Looking up {}".format(position, len(codes), code))
        try:
            data = client.execute(SYNC, "get_odoo_data", ACCOUNT, code,
                                  context=dict(CONTEXT))
            if not data:
                # get_odoo_data hides HTTP status: False is not proof of a 404.
                lookup_errors[code] = ("missing_or_lookup_failed",
                                       "Missing in Odoo or lookup failed (HTTP status unavailable)")
            elif not isinstance(data, dict):
                lookup_errors[code] = ("lookup_error", "Invalid Odoo account response")
            else:
                odoo_id = data.get("odoo_id")
                metadata = data.get("metadata") or []
                if (not isinstance(odoo_id, integer_types) or isinstance(odoo_id, bool)
                        or odoo_id <= 0 or not isinstance(metadata, list) or not metadata
                        or not isinstance(metadata[0], dict)
                        or metadata[0].get("code") != code):
                    lookup_errors[code] = ("lookup_error", "Invalid Odoo account response")
                else:
                    destinations[code] = odoo_id
        except Exception as exc:
            lookup_errors[code] = ("lookup_error", "Odoo lookup failed: {}".format(exc))
        if code in lookup_errors:
            print_message("WARNING {}: {}".format(code, lookup_errors[code][1]))
        else:
            print_message("FOUND {} (Odoo ID {})".format(code, destinations[code]))

    updates = []
    for position, (code, target) in enumerate(mappings.items(), 1):
        account = by_code[code][0]
        print_message("[ERP {}/{}] Checking {} -> {}".format(
            position, len(mappings), code, target))
        if target in lookup_errors:
            status, message = lookup_errors[target]
            updates.append({"account": account, "syncs": [], "target": target,
                            "odoo_id": False, "unchanged": False,
                            "skip_reason": message, "status": status, "message": message})
            print_message("SKIPPED {}: {}".format(code, message))
            continue
        syncs = read_syncs(client, account["id"])
        if len(syncs) > 1:
            raise ValueError("Multiple sync records for ERP account {}".format(code))
        unchanged = (account["odoo_account_code"] == target and len(syncs) == 1
                     and syncs[0]["odoo_id"] == destinations[target]
                     and syncs[0]["sync_state"] == "synced")
        updates.append({"account": account, "syncs": syncs, "target": target,
                        "odoo_id": destinations[target], "unchanged": unchanged,
                        "status": "unchanged" if unchanged else "would_remap", "message": ""})
        print_message("{} {} -> {} (Odoo ID {})".format(
            "UNCHANGED" if unchanged else "WOULD REMAP", code, target, destinations[target]))
    return updates


def save_backup(path, input_path, updates):
    payload = {
        "format_version": 1,
        "created_at": datetime.utcnow().isoformat() + "+00:00",
        "input": os.path.realpath(input_path),
        "updates": updates,
    }
    content = text(json.dumps(payload, ensure_ascii=False, indent=2)) + "\n"
    # O_EXCL preserves exclusive creation on Python 2; keep backups private.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as destination:
        destination.write(content.encode("utf-8"))
        destination.flush()
        os.fsync(destination.fileno())


def apply_updates(client, updates, report=None):
    updated = 0
    for position, item in enumerate(updates, 1):
        if item.get("skip_reason") or item["unchanged"]:
            continue
        account = item["account"]
        account_id = account["id"]
        stage = "checking for concurrent changes"
        try:
            print_message("[Apply {}/{}] {}: {}".format(
                position, len(updates), account["code"], stage))
            current = client.execute(ACCOUNT, "read", [account_id], ACCOUNT_FIELDS,
                                     context=dict(CONTEXT))
            if current != [account] or read_syncs(client, account_id) != item["syncs"]:
                raise RuntimeError("ERP account or sync changed since validation")
            stage = "deleting old local mapping"
            print_message("{}: {}".format(account["code"], stage))
            if item["syncs"]:
                result = client.execute(SYNC, "unlink", [s["id"] for s in item["syncs"]])
                if not result:
                    raise RuntimeError("Mapping deletion was not confirmed")
            stage = "writing Odoo account code"
            print_message("{}: {}".format(account["code"], stage))
            if not client.execute(ACCOUNT, "write", [account_id],
                                  {"odoo_account_code": item["target"]}):
                raise RuntimeError("Account write was not confirmed")
            stage = "synchronizing"
            print_message("{}: {}".format(account["code"], stage))
            # Never use from_fk_sync: it can reuse a stale local mapping.
            result = client.execute(SYNC, "common_sync_model_create_update",
                                    ACCOUNT, "sync", account_id, context={})
            stage = "verifying final mapping"
            print_message("{}: {}".format(account["code"], stage))
            syncs = read_syncs(client, account_id)
            current = client.execute(ACCOUNT, "read", [account_id],
                                     ["odoo_account_code"], context=dict(CONTEXT))
            if (not isinstance(result, (list, tuple)) or len(result) != 2
                    or result[0] != item["odoo_id"] or len(syncs) != 1
                    or syncs[0]["odoo_id"] != item["odoo_id"]
                    or syncs[0]["sync_state"] != "synced"
                    or current[0]["odoo_account_code"] != item["target"]):
                raise RuntimeError("Final code or synchronized mapping does not match")
        except Exception as exc:
            item["status"] = "error"
            item["message"] = "Failure while {}: {}; partial changes may remain".format(stage, exc)
            if report is not None:
                report.write(updates)
            raise RuntimeError(
                "Stopped at ERP {} (ID {}) while {}: {}. {} accounts completed; "
                "partial changes may remain. Inspect the backup and ERP before retrying."
                .format(account["code"], account_id, stage, exc, updated))
        updated += 1
        item["status"] = "updated"
        item["message"] = "Remapped and verified"
        if report is not None:
            report.write(updates)
        print_message("UPDATED {} -> {} (Odoo ID {})".format(
            account["code"], item["target"], item["odoo_id"]))
    return updated


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.realpath(__file__))), "mapeig_261102.csv"),
        help="Input ERP;Odoo CSV")
    parser.add_argument("--apply", action="store_true", help="Apply validated changes")
    parser.add_argument("--backup", help="New JSON backup path; required with --apply")
    parser.add_argument("--report", help="New CSV report path (default: timestamped beside input)")
    args = parser.parse_args(argv)
    if args.apply and not args.backup:
        parser.error("--apply requires --backup")
    mappings = read_mappings(args.input)
    import dbconfig
    from erppeek import Client

    print_message("Connecting to ERP")
    client = Client(**dbconfig.erppeek)
    updates = prepare_updates(client, mappings)
    skipped = sum(bool(item.get("skip_reason")) for item in updates)
    changed = sum(not item["unchanged"] and not item.get("skip_reason") for item in updates)
    print_message("Checked {} accounts; {} require remapping; {} skipped".format(
        len(updates), changed, skipped))
    report_path = args.report or "{}.report-{}.csv".format(
        os.path.splitext(args.input)[0], datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ"))
    report = Report(report_path)
    try:
        if args.apply:
            for item in updates:
                if item["status"] == "would_remap":
                    item["status"] = "pending"
        report.write(updates)
        print_message("Report saved to {}".format(report_path))
        if not args.apply:
            print_message("Validation only: no ERP/Odoo records changed")
            return 2 if skipped else 0
        # Skipped accounts will not be touched; do not claim their empty syncs are a backup.
        save_backup(args.backup, args.input,
                    [item for item in updates if not item.get("skip_reason")])
        print_message("Backup saved to {}".format(args.backup))
        count = apply_updates(client, updates, report=report)
        print_message("Remapped and verified {} accounts; {} skipped".format(count, skipped))
        return 2 if skipped else 0
    finally:
        report.close()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        print_message("ERROR: {}".format(error), stream=sys.stderr)
        sys.exit(1)
