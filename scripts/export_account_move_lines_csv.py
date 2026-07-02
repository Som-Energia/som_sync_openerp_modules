# -*- coding: utf-8 -*-
"""
Script per exportar assentaments de bancs a un excel

   python scripts/export_account_move_lines_csv.py \
     --account 572000000005 \
     --date-from 2026-01-01 \
     --date-to 2026-01-31 \
     --output /tmp/moviments_572_gener_2026.csv
"""
from __future__ import print_function, unicode_literals

import io
import re
import sys

try:
    import argparse
except ImportError:
    argparse = None

import dbconfig
from erppeek import Client


def to_text(value):
    if value is None:
        return u""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return u"%s" % value


REMESA_FAKE_RE = re.compile(r"^\d{4}-\d{10,}$")
PAYMENT_ORDER_RE = re.compile(r"^pagament\s+(\d{4}-\d{10,})$", re.IGNORECASE)
INVOICE_HINT_RE = re.compile(r"\b(FPE\d+|RE/[^\s;]+|RG/[^\s;]+)\b", re.IGNORECASE)


def _extract_m2o_id(value):
    if isinstance(value, (list, tuple)) and value:
        try:
            return int(value[0])
        except Exception:
            return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except Exception:
            return None
    if isinstance(value, (str, bytes)):
        txt = to_text(value).strip()
        if txt.isdigit():
            return int(txt)
    return None


class MoveInvoiceHintResolver(object):
    def __init__(self, client):
        self.client = client
        self.cache = {}

    def _invoice_info_from_any_model(self, invoice_id):
        invoice_id = _extract_m2o_id(invoice_id)
        if not invoice_id:
            return None, None

        for model, fields in [
            ("giscedata.facturacio.factura", ["number", "name", "ref"]),
            ("account.invoice", ["number", "reference", "internal_number", "move_name"]),
        ]:
            try:
                row = self.client.execute(model, "read", [invoice_id], fields)
                row = row[0] if isinstance(row, list) and row else row
                if not row:
                    continue
                for f in fields:
                    val = to_text(row.get(f)).strip()
                    if val:
                        m = INVOICE_HINT_RE.search(val)
                        if m:
                            return to_text(m.group(1)).upper(), invoice_id
                        return val, invoice_id
            except Exception:
                continue
        return None, None

    def _invoice_number_from_any_model(self, invoice_id):
        return self._invoice_info_from_any_model(invoice_id)[0]

    def invoice_info_for_line(self, line):
        if not isinstance(line, dict):
            return None, None
        for field_name in ["invoice_id", "factura_id", "invoice", "factura"]:
            if field_name in line:
                number, invoice_id = self._invoice_info_from_any_model(line.get(field_name))
                if number:
                    return number, invoice_id
        return None, None

    def invoice_hint_for_line(self, line):
        return self.invoice_info_for_line(line)[0]

    def invoice_info_for_move(self, move_id):
        move_id = _extract_m2o_id(move_id)
        if not move_id:
            return None, None
        if move_id in self.cache:
            return self.cache[move_id]

        try:
            ids = self.client.AccountMoveLine.search([("move_id", "=", move_id)])
            if not ids:
                self.cache[move_id] = (None, None)
                return None, None
            lines = self.client.AccountMoveLine.read(
                ids, ["name", "ref", "invoice_id", "factura_id", "invoice", "factura"])
        except Exception:
            self.cache[move_id] = (None, None)
            return None, None

        candidates = {}
        for ln in lines or []:
            direct_number, direct_id = self.invoice_info_for_line(ln)
            if direct_number:
                candidates[direct_number] = direct_id
            for txt in (to_text(ln.get("ref")), to_text(ln.get("name"))):
                m = INVOICE_HINT_RE.search(txt or "")
                if m:
                    candidates[to_text(m.group(1)).upper()] = None

        value = list(candidates.items())[0] if len(candidates) == 1 else (None, None)
        self.cache[move_id] = value
        return value

    def invoice_hint_for_move(self, move_id):
        return self.invoice_info_for_move(move_id)[0]


class RemesaFacturaResolver(object):
    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.remesa_fields = self._safe_fields_get("giscedata.remesa.f1")
        self.invoice_fields = self._safe_fields_get("account.invoice")

    def _safe_fields_get(self, model):
        try:
            fields = self.client.execute(model, "fields_get")
            return fields if isinstance(fields, dict) else {}
        except Exception:
            return {}

    def _search_one(self, model, domain):
        try:
            ids = self.client.execute(model, "search", domain, 0, 1)
            return ids[0] if ids else None
        except Exception:
            return None

    def _search_ids(self, model, domain, limit=20):
        try:
            return self.client.execute(model, "search", domain, 0, limit) or []
        except Exception:
            return []

    def _read(self, model, rec_id, fields):
        if not rec_id:
            return None
        try:
            data = self.client.execute(model, "read", [rec_id], fields)
            if isinstance(data, list):
                return data[0] if data else None
            return data
        except Exception:
            return None

    def _invoice_number(self, invoice_id):
        return self._invoice_info(invoice_id)[0]

    def _invoice_info(self, invoice_id):
        if not invoice_id:
            return None, None

        number_candidates = ["number", "reference", "internal_number", "move_name"]
        usable = [f for f in number_candidates if f in self.invoice_fields] or ["number"]
        inv = self._read("account.invoice", invoice_id, usable)
        if not inv:
            return None, None

        for field_name in usable:
            value = to_text(inv.get(field_name)).strip()
            if value:
                return value, invoice_id
        return None, None

    def _find_remesa_ids(self, code):
        terms = [code, u"Remesa %s" % code]
        char_fields = [
            name for name, meta in self.remesa_fields.items()
            if to_text(meta.get("type")) in ("char", "text")
        ]
        preferred = [f for f in ["name", "codi", "code", "reference", "ref"] if f in char_fields]
        candidates = preferred + [f for f in char_fields if f not in preferred]

        for field_name in candidates:
            for term in terms:
                for op in ("=", "ilike"):
                    ids = self._search_ids("giscedata.remesa.f1", [
                                           (field_name, op, term)], limit=20)
                    if ids:
                        return ids
        return []

    def _invoice_from_direct_rel(self, remesa_id):
        rel_fields = [
            name for name, meta in self.remesa_fields.items()
            if to_text(meta.get("type")) == "many2one"
            and to_text(meta.get("relation")) == "account.invoice"
        ]
        if not rel_fields:
            rel_fields = [f for f in ["invoice_id", "factura_id",
                                      "invoice", "factura"] if f in self.remesa_fields]
        if not rel_fields:
            return None, None

        remesa = self._read("giscedata.remesa.f1", remesa_id, rel_fields)
        if not remesa:
            return None, None

        for field_name in rel_fields:
            invoice_id = _extract_m2o_id(remesa.get(field_name))
            number = self._invoice_number(invoice_id)
            if number:
                return number, invoice_id
        return None, None

    def _invoice_from_related_lines(self, remesa_id):
        rel_fields = [
            name for name, meta in self.remesa_fields.items()
            if to_text(meta.get("type")) in ("one2many", "many2many")
        ]

        candidates = {}
        for field_name in rel_fields:
            meta = self.remesa_fields.get(field_name, {})
            relation_model = to_text(meta.get("relation"))
            if not relation_model:
                continue

            remesa = self._read("giscedata.remesa.f1", remesa_id, [field_name])
            rel_ids = (remesa or {}).get(field_name) or []
            if not isinstance(rel_ids, list) or not rel_ids:
                continue

            rel_meta = self._safe_fields_get(relation_model)
            invoice_m2o_fields = [
                n for n, m in rel_meta.items()
                if to_text(m.get("type")) == "many2one"
                and to_text(m.get("relation")) == "account.invoice"
            ]
            if (relation_model == "giscedata.facturacio.factura"
                    and "invoice_id" not in invoice_m2o_fields):
                invoice_m2o_fields.append("invoice_id")
            for rel_id in rel_ids[:200]:
                if invoice_m2o_fields:
                    rel_row = self._read(relation_model, rel_id, invoice_m2o_fields)
                    if rel_row:
                        for m2o in invoice_m2o_fields:
                            invoice_id = _extract_m2o_id(rel_row.get(m2o))
                            number = self._invoice_number(invoice_id)
                            if number:
                                candidates[number] = invoice_id

                for num_field in ["numfactura", "number", "invoice_number", "name"]:
                    if num_field in rel_meta:
                        rel_row = self._read(relation_model, rel_id, [num_field])
                        value = to_text((rel_row or {}).get(num_field)).strip()
                        if value and ("/" in value or value.upper().startswith("FPE")):
                            candidates[value] = None

        if len(candidates) == 1:
            return list(candidates.items())[0]
        return None, None

    def resolve_invoice(self, remesa_code):
        code = to_text(remesa_code).strip()
        if code in self.cache:
            return self.cache[code]

        if not code:
            self.cache[code] = (None, None)
            return None, None

        remesa_ids = self._find_remesa_ids(code)
        for remesa_id in remesa_ids:
            number, invoice_id = self._invoice_from_direct_rel(remesa_id)
            if number:
                self.cache[code] = (number, invoice_id)
                return number, invoice_id

            number, invoice_id = self._invoice_from_related_lines(remesa_id)
            if number:
                self.cache[code] = (number, invoice_id)
                return number, invoice_id

        self.cache[code] = (None, None)
        return None, None

    def resolve_invoice_number(self, remesa_code):
        return self.resolve_invoice(remesa_code)[0]


class PaymentOrderResolver(object):
    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.order_cache = {}

    def _extract_remesa_code(self, value):
        txt = to_text(value).strip()
        match = re.search(r"\bremesa\s+(.+)$", txt, re.IGNORECASE)
        if match:
            return to_text(match.group(1)).strip()
        match = PAYMENT_ORDER_RE.match(txt)
        if match:
            return to_text(match.group(1)).strip()
        return u""

    def _resolve_order(self, remesa_code):
        if remesa_code in self.order_cache:
            return self.order_cache[remesa_code]

        if not remesa_code:
            self.order_cache[remesa_code] = (u"", u"")
            return self.order_cache[remesa_code]

        order_model = self.client.model("payment.order")
        order_ids = order_model.search([("reference", "=", remesa_code)])
        if not order_ids:
            order_ids = order_model.search([("name", "=", remesa_code)])

        order_name = u""
        order_id = u""
        if len(order_ids) == 1:
            order = order_model.read(order_ids[0], ["id", "name", "reference"])
            order_name = to_text(order.get("name") or order.get("reference")).strip()
            order_id = to_text(order.get("id"))

        if not order_id:
            remesa_model = self.client.model("giscedata.remesa.f1")
            remesa_ids = remesa_model.search([("name", "=", remesa_code)])
            if len(remesa_ids) == 1:
                remesa = remesa_model.read(remesa_ids[0], ["id", "name"])
                order_name = to_text(remesa.get("name") or remesa_code).strip()
                order_id = to_text(remesa.get("id"))

        self.order_cache[remesa_code] = (order_name, order_id)
        return self.order_cache[remesa_code]

    def resolve_for_line(self, line_name, line_ref=u""):
        cache_key = (to_text(line_name), to_text(line_ref))
        if cache_key in self.cache:
            return self.cache[cache_key]

        remesa_code = self._extract_remesa_code(line_name) or self._extract_remesa_code(line_ref)
        value = self._resolve_order(remesa_code)
        self.cache[cache_key] = value
        return value


class DevolucioResolver(object):
    def __init__(self, client):
        self.client = client
        self.cache = {}
        self.lines_cache = {}

    def _get_devolucio_total(self, devolucio_id, line_ids):
        if devolucio_id in self.lines_cache:
            return self.lines_cache[devolucio_id]

        total = 0.0
        if line_ids:
            line_model = self.client.model("giscedata.facturacio.devolucio.linia")
            rows = line_model.read(line_ids, ["import"])
            if isinstance(rows, dict):
                rows = [rows]
            total = round(sum(float(row.get("import") or 0.0) for row in rows), 2)

        self.lines_cache[devolucio_id] = total
        return total

    def resolve_for_line(self, line_name, line_date, signed_amount):
        cache_key = (
            to_text(line_name),
            to_text(line_date),
            round(abs(float(signed_amount or 0.0)), 2),
        )
        if cache_key in self.cache:
            return self.cache[cache_key]

        if u"devoluc" not in to_text(line_name).lower():
            self.cache[cache_key] = (u"", u"")
            return self.cache[cache_key]

        amount = round(abs(float(signed_amount or 0.0)), 2)
        devolucio_model = self.client.model("giscedata.facturacio.devolucio")
        devolucio_ids = devolucio_model.search([("date", "=", line_date)])

        matches = []
        for devolucio_id in devolucio_ids:
            devolucio = devolucio_model.read(devolucio_id, ["id", "name", "linies_ids"])
            total = self._get_devolucio_total(devolucio_id, devolucio.get("linies_ids") or [])
            if total == amount:
                matches.append((to_text(devolucio.get("name")).strip(), to_text(devolucio_id)))

        value = matches[0] if len(matches) == 1 else (u"", u"")
        self.cache[cache_key] = value
        return value


class CounterpartAccountResolver(object):
    def __init__(self, client, bank_account_ids):
        self.client = client
        self.bank_account_ids = set(bank_account_ids or [])
        self.cache = {}

    def resolve_for_move(self, move_id):
        move_id = _extract_m2o_id(move_id)
        if move_id in self.cache:
            return self.cache[move_id]

        if not move_id:
            self.cache[move_id] = u""
            return self.cache[move_id]

        try:
            line_ids = self.client.AccountMoveLine.search([("move_id", "=", move_id)])
            lines = self.client.AccountMoveLine.read(line_ids, ["account_id"]) if line_ids else []
        except Exception:
            lines = []

        counterparts = []
        seen = set()
        for line in lines or []:
            account = line.get("account_id")
            account_id = _extract_m2o_id(account)
            if not account_id or account_id in self.bank_account_ids:
                continue
            label = to_text(account[1] if isinstance(account, (list, tuple))
                            and len(account) > 1 else u"").strip()
            if label and label not in seen:
                seen.add(label)
                counterparts.append(label)

        self.cache[move_id] = u" | ".join(counterparts)
        return self.cache[move_id]


def classify_description(
        line_name, line_ref, line_data=None, move_id=None,
        move_hint_resolver=None, remesa_resolver=None):
    name = to_text(line_name).strip()
    ref = to_text(line_ref).strip()
    lower_name = name.lower()

    # Prioritat 1: pista de factura a la pròpia línia
    for candidate in (ref, name):
        m = INVOICE_HINT_RE.search(candidate or "")
        if m:
            return u"[FACTURA] %s" % to_text(m.group(1)).upper()

    # Prioritat 2: relació directa factura a la línia comptable
    if move_hint_resolver and isinstance(line_data, dict):
        direct = move_hint_resolver.invoice_hint_for_line(line_data)
        if direct:
            return u"[FACTURA] %s" % direct

    remesa_match = re.search(r"\bremesa\s+(.+)$", name, re.IGNORECASE)
    if remesa_match:
        remesa_code = remesa_match.group(1).strip()
        if REMESA_FAKE_RE.match(remesa_code) and remesa_resolver:
            invoice_number = remesa_resolver.resolve_invoice_number(remesa_code)
            if invoice_number:
                return u"[FACTURA] %s" % invoice_number
        return u"[REMESA] %s" % remesa_code

    payment_order_match = PAYMENT_ORDER_RE.match(name)
    if payment_order_match:
        return u"[REMESA] %s" % payment_order_match.group(1).strip()

    if u"comissió" in lower_name or u"comissio" in lower_name or u"comisión" in lower_name:
        return u"[COMISSIÓ] Comissió"

    if u"devoluc" in lower_name:
        return u"[DEVOLUCIONS] Devolucions"

    # Prioritat 4: pista de factura en altres línies del mateix assentament
    if move_hint_resolver:
        move_hint = move_hint_resolver.invoice_hint_for_move(move_id)
        if move_hint:
            return u"[FACTURA] %s" % move_hint

    if ref and re.search(r"\d", ref):
        return u"[FACTURA] %s" % ref

    return name or ref


def amount_signed(debit, credit):
    debit = float(debit or 0.0)
    credit = float(credit or 0.0)
    return debit - credit


def format_amount(value):
    return (u"%.2f" % value)


def lookup_invoice_id(client, invoice_value):
    invoice_value = to_text(invoice_value).strip()
    if not invoice_value:
        return u""
    invoice_model = client.model("account.invoice")
    for field_name in ["number", "reference", "move_name"]:
        invoice_ids = invoice_model.search([(field_name, "=", invoice_value)])
        if len(invoice_ids) == 1:
            return to_text(invoice_ids[0])
    return u""


def resolve_invoice_for_export(client, row, move_hint_resolver, remesa_resolver):
    number, invoice_id = move_hint_resolver.invoice_info_for_line(row)
    if number:
        return number, to_text(invoice_id or u"")

    remesa_match = re.search(r"\bremesa\s+(.+)$", to_text(row.get("name")).strip(), re.IGNORECASE)
    if remesa_match:
        remesa_code = remesa_match.group(1).strip()
        if REMESA_FAKE_RE.match(remesa_code):
            number, invoice_id = remesa_resolver.resolve_invoice(remesa_code)
            if number:
                return number, to_text(invoice_id or u"")

    for candidate in (row.get("ref"), row.get("name")):
        m = INVOICE_HINT_RE.search(to_text(candidate) or u"")
        if m:
            number = to_text(m.group(1)).upper()
            return number, lookup_invoice_id(client, number)

    ref = to_text(row.get("ref")).strip()
    if ref:
        invoice_id = lookup_invoice_id(client, ref)
        if invoice_id:
            return ref, invoice_id

    number, invoice_id = move_hint_resolver.invoice_info_for_move(row.get("move_id"))
    if number:
        return number, to_text(invoice_id or lookup_invoice_id(client, number))

    if ref and re.search(r"\d", ref):
        return ref, lookup_invoice_id(client, ref)

    return u"", u""


def enrich_description(
        desc, remesa_name=u"", devolucio_name=u"", invoice_number=u"", counterpart_label=u""):
    desc = to_text(desc).strip()
    if desc.startswith(u"[REMESA]") and remesa_name:
        desc = u"[REMESA] %s" % remesa_name
    elif desc.startswith(u"[DEVOLUCIONS]") and devolucio_name:
        desc = u"[DEVOLUCIONS] %s" % devolucio_name
    if invoice_number and invoice_number not in desc:
        desc = u"%s %s" % (desc, invoice_number)
    if counterpart_label and counterpart_label not in desc:
        desc = u"%s [%s]" % (desc, counterpart_label)
    return desc


def export_csv(account_code, date_from, date_to, output_path):
    client = Client(**dbconfig.erppeek)

    account_ids = client.AccountAccount.search([("code", "=", account_code)])
    if not account_ids:
        raise RuntimeError("No s'ha trobat el compte comptable: %s" % account_code)

    domain = [
        ("account_id", "in", account_ids),
        ("date", ">=", date_from),
        ("date", "<=", date_to),
    ]

    line_ids = client.AccountMoveLine.search(domain, order="date asc, id asc")
    if not line_ids:
        print("No hi ha moviments per als filtres indicats.")

    line_fields = client.execute("account.move.line", "fields_get") or {}
    wanted_fields = ["id", "date", "name", "ref", "move_id", "account_id", "invoice_id",
                     "factura_id", "invoice", "factura", "debit", "credit"]
    fields = [field for field in wanted_fields if field in line_fields]
    rows = client.AccountMoveLine.read(line_ids, fields) if line_ids else []

    # Defensa extra: alguns backends no garanteixen l'ordre del read(line_ids, ...)
    rows = sorted(rows, key=lambda r: (to_text(r.get("date")), int(r.get("id") or 0)))
    move_hint_resolver = MoveInvoiceHintResolver(client)
    remesa_resolver = RemesaFacturaResolver(client)
    payment_order_resolver = PaymentOrderResolver(client)
    devolucio_resolver = DevolucioResolver(client)
    counterpart_resolver = CounterpartAccountResolver(client, account_ids)

    unresolved_fake_remeses = set()

    with io.open(output_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(u"id;data;compte_comptable;descripcio;nom_remesa;num_factura;res_id;import\n")
        for row in rows:
            raw_name = to_text(row.get("name")).strip()
            signed = amount_signed(row.get("debit"), row.get("credit"))
            desc = classify_description(
                row.get("name"),
                row.get("ref"),
                row,
                row.get("move_id"),
                move_hint_resolver,
                remesa_resolver,
            )
            remesa_name, remesa_id = payment_order_resolver.resolve_for_line(
                row.get("name"), row.get("ref")
            )
            devolucio_name, devolucio_id = devolucio_resolver.resolve_for_line(
                row.get("name"), row.get("date"), signed
            )
            invoice_number, invoice_id = resolve_invoice_for_export(
                client, row, move_hint_resolver, remesa_resolver
            )
            counterpart_label = counterpart_resolver.resolve_for_move(row.get("move_id"))
            desc = enrich_description(
                desc,
                remesa_name=remesa_name,
                devolucio_name=devolucio_name,
                invoice_number=invoice_number,
                counterpart_label=counterpart_label,
            )

            export_name = remesa_name or devolucio_name
            export_res_id = invoice_id or remesa_id or devolucio_id
            remesa_match = re.search(r"\bremesa\s+(.+)$", raw_name, re.IGNORECASE)
            if remesa_match:
                remesa_code = remesa_match.group(1).strip()
                if REMESA_FAKE_RE.match(remesa_code) and desc.startswith(u"[REMESA]"):
                    unresolved_fake_remeses.add(remesa_code)

            line = u"%s;%s;%s;%s;%s;%s;%s;%s\n" % (
                to_text(row.get("id")),
                to_text(row.get("date")),
                account_code,
                desc.replace(u";", u","),
                export_name.replace(u";", u","),
                invoice_number.replace(u";", u","),
                export_res_id.replace(u";", u","),
                format_amount(signed),
            )
            fh.write(line)

    print("CSV generat: %s (%s linies)" % (output_path, len(rows)))
    if unresolved_fake_remeses:
        print("AVIS: %s remeses fake sense factura trobada" % len(unresolved_fake_remeses))
        print("Exemples: %s" % ", ".join(sorted(unresolved_fake_remeses)[:10]))


def parse_args(argv):
    if argparse is None:
        raise RuntimeError("argparse no disponible")

    parser = argparse.ArgumentParser(
        description="Exporta account.move.line a CSV amb classificació de descripcions"
    )
    parser.add_argument("--account", required=True, help="Codi compte comptable (ex: 572000000005)")
    parser.add_argument("--date-from", required=True, help="Data inici (YYYY-MM-DD)")
    parser.add_argument("--date-to", required=True, help="Data fi (YYYY-MM-DD)")
    parser.add_argument("--output", required=True, help="Ruta fitxer CSV de sortida")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    export_csv(args.account, args.date_from, args.date_to, args.output)


if __name__ == "__main__":
    main()
