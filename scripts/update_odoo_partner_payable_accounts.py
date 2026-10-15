#!/usr/bin/env python
"""Update Odoo 18 partner payable accounts from a UTF-8 old_code,new_code CSV.

Uses only Python's standard library. Dots and surrounding whitespace are removed
from both input codes before validation and matching; leading zeros are preserved.
Compatible with Python 2.7 and Python 3.
The header must be old_code,new_code (comma separated). Empty rows and rows
with only a destination are ignored; conflicting or malformed rows are errors.

Example:
    python scripts/update_odoo_partner_payable_accounts.py \
        --url https://odoo.example.org --db DATABASE --username LOGIN \
        --input mapping.csv --company-id 1 --dry-run

Set ODOO_API_KEY or enter the key/password at the hidden prompt. Remove --dry-run
to apply. Each XML-RPC write commits separately; the CSV records batch outcomes.
Only property_account_payable_id is written, in the selected company context.
Only company-type partners are direct update candidates, including shared and
archived companies and effective ir.default values. Only companies are read,
checked and reported; Odoo's ORM handles propagation to their contacts.
Destinations 400900100, 400900200 and 400900800 are explicitly skipped, keeping
the affected companies unchanged and recording them in the report.
Use --limit N to read and process at most N companies, ordered by ID. Unchanged
and skipped companies count towards the limit, so fewer than N may be updated.
Destination validation still covers the full input CSV.
"""
from __future__ import print_function, unicode_literals

import argparse
import codecs
from collections import defaultdict
import csv
from datetime import datetime
import getpass
import io
import os
import sys

try:
    from http.client import HTTPException
    import xmlrpc.client as xmlrpc_client
except ImportError:
    from httplib import HTTPException
    import xmlrpclib as xmlrpc_client


PY2 = sys.version_info[0] == 2
DEFAULT_INPUT = os.path.join(os.path.dirname(__file__), "partner_payable_account_mapping.csv")
FIELD = "property_account_payable_id"
SKIP_DESTINATION_CODES = {"400900100", "400900200", "400900800"}
REPORT_FIELDS = [
    "partner_id", "partner_name", "old_account_id", "old_code",
    "new_account_id", "new_code", "reason", "status",
]


def print_message(message, stream=None):
    """Keep API names and errors printable as UTF-8 even under Python 2."""
    stream = stream or sys.stdout
    if PY2 and isinstance(message, type(u"")):
        message = message.encode("utf-8")
    print(message, file=stream)
    stream.flush()


class ReportWriter(csv.DictWriter):
    """Python 2's csv module requires encoded bytes, including Unicode names."""

    def writerow(self, rowdict):
        if PY2:
            rowdict = {key: value.encode("utf-8") if isinstance(value, type(u"")) else value
                       for key, value in rowdict.items()}
        return csv.DictWriter.writerow(self, rowdict)

    def writerows(self, rowdicts):
        for row in rowdicts:
            self.writerow(row)


def open_report(path):
    """Create exclusively without relying on Python 3's open(mode='x')."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    if PY2:
        return os.fdopen(descriptor, "wb")
    return io.open(descriptor, "w", newline="", encoding="utf-8-sig")


def read_mappings(path):
    """Read string codes without dots, accepting UTF-8 with or without a BOM."""
    mappings, origins, errors = {}, {}, []
    ignored = []
    with io.open(path, newline="", encoding="utf-8-sig") as csv_file:
        lines = (line.encode("utf-8") for line in csv_file) if PY2 else csv_file
        reader = csv.DictReader(lines, strict=True)
        if reader.fieldnames != ["old_code", "new_code"]:
            raise ValueError("CSV header must be old_code,new_code (comma separated)")
        for row in reader:
            number = reader.line_num
            if None in row or any(value is None for value in row.values()):
                errors.append("Row {}: expected exactly two columns".format(number))
                continue
            source, destination = row["old_code"], row["new_code"]
            if PY2:
                source, destination = source.decode("utf-8"), destination.decode("utf-8")
            source = source.strip().replace(".", "")
            destination = destination.strip().replace(".", "")
            if not source:
                if destination:
                    ignored.append(number)
                continue
            if not destination:
                errors.append("Row {}: source {} has no destination".format(number, source))
                continue
            if source in mappings and mappings[source] != destination:
                errors.append("{}: row {} -> {}, row {} -> {}".format(
                    source, origins[source], mappings[source], number, destination))
            else:
                mappings[source], origins[source] = destination, number
    if errors:
        raise ValueError("Invalid mapping:\n" + "\n".join(errors))
    if not mappings:
        raise ValueError("CSV contains no mappings")
    print_message("CSV: {}; {} mappings".format(path, len(mappings)))
    if ignored:
        print_message("Ignored rows without source: {}".format(", ".join(map(str, ignored))))
    return mappings


def many2one_id(value):
    return value[0] if value else False


def chunks(values, size=200):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def read_partners(call, company_id, context, limit=None):
    """Read only company partners, using bounded responses and an ID cursor."""
    if limit is not None and limit <= 0:
        raise ValueError("Partner limit must be a positive integer")
    partners = []
    last_id = 0
    while True:
        page_size = 200 if limit is None else min(200, limit - len(partners))
        if page_size == 0:
            break
        try:
            page = call("res.partner", "search_read", [[
                ("id", ">", last_id),
                ("is_company", "=", True),
                "|", ("company_id", "=", company_id), ("company_id", "=", False),
            ]], {"fields": ["name", FIELD],
                 "context": context, "order": "id", "limit": page_size})
        except (HTTPException, IOError, OSError) as exc:
            raise RuntimeError(
                "Connection interrupted while reading partners after ID {} "
                "({} read). No partner updates have started. "
                "Run the command again. Details: {}".format(last_id, len(partners), exc))
        if not page:
            break
        if page[0]["id"] <= last_id or page[-1]["id"] < page[0]["id"]:
            raise RuntimeError("Odoo returned an invalid partner ID page")
        partners.extend(page)
        last_id = page[-1]["id"]
        print_message("Company partners read: {} (last ID: {})".format(len(partners), last_id))

    return partners


def prepare_plan(call, mappings, company_id, limit=None):
    if limit is not None and limit <= 0:
        raise ValueError("Partner limit must be a positive integer")
    context = {"allowed_company_ids": [company_id], "active_test": False}
    companies = call("res.company", "search_read", [[("id", "=", company_id)]],
                     {"fields": ["name"], "context": context})
    if len(companies) != 1:
        raise ValueError("Company {} is not accessible".format(company_id))
    print_message("Company: {} (ID {})".format(companies[0]["name"], company_id))
    accounts = {}
    for codes in chunks(sorted(set(mappings) | set(mappings.values()))):
        records = call("account.account", "search_read", [[
            ("code", "in", codes), ("company_ids", "in", [company_id]),
        ]], {"fields": ["code", "account_type", "deprecated"], "context": context})
        for account in records:
            if account["code"] in accounts:
                raise ValueError("Multiple accounts match {}".format(account["code"]))
            accounts[account["code"]] = account
    errors = []
    for code in sorted(set(mappings.values())):
        account = accounts.get(code)
        if not account:
            errors.append("Destination not found: {}".format(code))
        elif code in SKIP_DESTINATION_CODES:
            print_message("SKIPPED destination {}: excluded pending-invoice account".format(code))
        elif account["deprecated"] or account["account_type"] != "liability_payable":
            errors.append("Destination {} must be a non-deprecated payable account".format(code))
    if errors:
        raise ValueError("\n".join(errors))
    partners = read_partners(call, company_id, context, limit=limit)
    by_id = {p["id"]: p for p in partners}
    destinations = {accounts[source]["id"]: accounts[target]
                    for source, target in mappings.items() if source in accounts}
    counts = defaultdict(int)
    desired = {}
    for partner in partners:
        old_id = many2one_id(partner[FIELD])
        if old_id in destinations:
            counts[old_id] += 1
            desired[partner["id"]] = destinations[old_id]
    for source, target in mappings.items():
        account = accounts.get(source)
        count = counts[account["id"]] if account else 0
        print_message("{} -> {}: {} partners{}".format(
            source, target, count, " (source account not found)" if not account else ""))

    skipped = {pid: "excluded destination {}".format(target["code"])
               for pid, target in desired.items() if target["code"] in SKIP_DESTINATION_CODES}

    # Only companies are planned; Odoo handles synchronization to their contacts.
    owners = {pid: pid for pid, account in desired.items()
              if pid not in skipped and many2one_id(by_id[pid][FIELD]) != account["id"]}

    rows = []
    codes_by_id = {a["id"]: a["code"] for a in accounts.values()}
    for pid in sorted(set(owners) | set(skipped)):
        owner = owners.get(pid)
        partner, target = by_id[pid], desired[pid]
        old_id = many2one_id(partner[FIELD])
        rows.append(dict(
            partner_id=pid, partner_name=partner["name"],
            old_account_id=old_id or "", old_code=codes_by_id.get(old_id, ""),
            new_account_id=target["id"], new_code=target["code"],
            reason=skipped.get(pid) or "mapping",
            status="skipped_destination" if pid in skipped else "planned", owner=owner,
        ))
    print_message("Plan: {} changed companies; skipped companies: {}".format(
        len(owners), len(skipped)))
    return rows, context


def check_accounts(call, rows, context, expected_field):
    expected = {r["partner_id"]: r[expected_field] or False for r in rows}
    for ids in chunks(list(expected)):
        records = call("res.partner", "read", [ids], {"fields": [FIELD], "context": context})
        actual = {r["id"]: many2one_id(r[FIELD]) for r in records}
        for pid in ids:
            if actual.get(pid) != expected[pid]:
                raise RuntimeError("Partner {}: expected account {}, got {}".format(
                    pid, expected[pid], actual.get(pid)))


def execute_plan(call, rows, context, report, dry_run=False):
    # Exclusive creation avoids overwriting a previous run's audit file.
    with open_report(report) as output:
        if PY2:
            output.write(codecs.BOM_UTF8)
        writer = ReportWriter(output, fieldnames=REPORT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        if dry_run:
            for row in rows:
                writer.writerow(dict(row, status="would_update")
                                if row["status"] == "planned" else row)
            return
        # Save the complete snapshot before the first remote write.
        writer.writerows(rows)
        output.flush()
        groups = defaultdict(list)
        for row in rows:
            if row["status"] == "planned":
                groups[row["new_account_id"]].append(row)
        for target_id, group in groups.items():
            direct_ids = sorted({row["owner"] for row in group})
            for ids in chunks(direct_ids):
                affected = [r for r in group if r["owner"] in ids]
                try:
                    check_accounts(call, affected, context, "old_account_id")
                except Exception:
                    writer.writerows(dict(r, status="not_written_precheck_failed")
                                     for r in affected)
                    output.flush()
                    raise
                try:
                    result = call("res.partner", "write", [ids, {FIELD: target_id}],
                                  {"context": context})
                    if not result:
                        raise RuntimeError("Odoo did not confirm the update")
                    check_accounts(call, affected, context, "new_account_id")
                except Exception:
                    # A transport failure can happen after the remote commit.
                    writer.writerows(dict(r, status="error_check_odoo") for r in affected)
                    output.flush()
                    raise
                writer.writerows(dict(r, status="updated") for r in affected)
                output.flush()
                print_message("UPDATED {} partners to account ID {}".format(
                    len(affected), target_id))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", required=True, help="Odoo server URL")
    parser.add_argument("--db", required=True, help="Odoo database name")
    parser.add_argument("--username", required=True, help="Odoo user login")
    parser.add_argument("--input", default=DEFAULT_INPUT,
                        help="UTF-8 old_code,new_code CSV (default: %(default)s)")
    parser.add_argument("--company-id", type=int, default=1)
    parser.add_argument("--limit", type=int,
                        help="Maximum companies to read and process, ordered by ID (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to Odoo")
    parser.add_argument("--report", help="New output CSV (must not exist)")
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be a positive integer")
    mappings = read_mappings(args.input)
    secret = os.environ.get("ODOO_API_KEY") or getpass.getpass("Odoo API key/password: ")
    url = args.url.rstrip("/")
    common = xmlrpc_client.ServerProxy(url + "/xmlrpc/2/common")
    uid = common.authenticate(args.db, args.username, secret, {})
    if not uid:
        raise RuntimeError("Odoo authentication failed")
    models = xmlrpc_client.ServerProxy(url + "/xmlrpc/2/object")

    def call(model, method, positional, keyword):
        return models.execute_kw(args.db, uid, secret, model, method, positional, keyword)

    rows, context = prepare_plan(call, mappings, args.company_id, limit=args.limit)
    report = args.report or "partner_payable_accounts_{}{}.csv".format(
        datetime.now().strftime("%Y%m%d_%H%M%S_%f"), "_dry_run" if args.dry_run else "")
    print_message("Report: {} (initial snapshot followed by batch outcomes)".format(
        os.path.abspath(report)))
    execute_plan(call, rows, context, report, args.dry_run)
    print_message("{} {} partners; skipped: {}".format(
        "Would update" if args.dry_run else "Updated",
        sum(r["status"] == "planned" for r in rows),
        sum(r["status"] == "skipped_destination" for r in rows)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (IOError, OSError, ValueError, RuntimeError, KeyError, csv.Error,
            HTTPException, xmlrpc_client.Error) as exc:
        print_message("ERROR: {}".format(exc), stream=sys.stderr)
        sys.exit(1)
