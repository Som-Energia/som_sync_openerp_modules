# -*- coding: utf-8 -*-
"""Compatibilitat Python 2.7/3 per als scripts del procés d'obertura."""

from __future__ import print_function, unicode_literals

import csv
import io
import json
import sys
from datetime import datetime

try:
    integer_types = (int, long)
    text_type = unicode
except NameError:
    integer_types = (int,)
    text_type = str

PY2 = sys.version_info[0] == 2


def is_integer(value):
    return isinstance(value, integer_types) and not isinstance(value, bool)


def text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return text_type(value)


def parse_date(value):
    result = datetime.strptime(value, "%Y-%m-%d").date()
    if result.isoformat() != value:
        raise ValueError("La data ha de tenir format YYYY-MM-DD")
    return result


def utc_now():
    return datetime.utcnow().isoformat() + "+00:00"


def read_json(path):
    with io.open(text(path), "r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path, payload):
    content = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with io.open(text(path), "w", encoding="utf-8") as stream:
        stream.write(text(content))


def write_csv(path, fields, rows):
    stream = open(text(path), "wb") if PY2 else io.open(
        text(path), "w", encoding="utf-8", newline="")
    with stream:
        writer = csv.writer(stream, delimiter=str(";"))

        def cell(value):
            if PY2 and isinstance(value, text_type):
                return value.encode("utf-8")
            return value

        writer.writerow([cell(field) for field in fields])
        for row in rows:
            writer.writerow([cell(row[field]) for field in fields])


def print_message(message, file=None):
    stream = file if file is not None else sys.stdout
    message = text(message) + "\n"
    stream.write(message.encode("utf-8") if PY2 else message)
