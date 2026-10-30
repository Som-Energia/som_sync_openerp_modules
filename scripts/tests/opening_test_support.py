# -*- coding: utf-8 -*-
"""Utilitats de proves per a executar la mateixa suite en Python 2.7 i 3."""

from __future__ import print_function, unicode_literals

import csv
import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import contextmanager

try:
    from unittest.mock import Mock, call, patch
except ImportError:
    from mock import Mock, call, patch

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
__all__ = ["Mock", "call", "patch", "SCRIPTS", "TestCase", "StringIO", "Namespace",
           "temporary_directory", "redirect_stdout", "redirect_stderr", "read_text",
           "read_bytes", "write_text", "read_csv"]


class TestCase(unittest.TestCase):
    if not hasattr(unittest.TestCase, "assertRaisesRegex"):
        @contextmanager
        def assertRaisesRegex(self, exception, pattern):
            with self.assertRaises(exception) as caught:
                yield caught
            self.assertRegexpMatches(caught.exception.args[0], pattern)


class StringIO(io.StringIO):
    def write(self, value):
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return super(StringIO, self).write(value)


class Namespace(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


@contextmanager
def temporary_directory():
    path = tempfile.mkdtemp()
    try:
        yield path
    finally:
        shutil.rmtree(path)


@contextmanager
def redirect_stdout(stream):
    previous = sys.stdout
    sys.stdout = stream
    try:
        yield stream
    finally:
        sys.stdout = previous


@contextmanager
def redirect_stderr(stream):
    previous = sys.stderr
    sys.stderr = stream
    try:
        yield stream
    finally:
        sys.stderr = previous


def read_text(path):
    with io.open(path, encoding="utf-8") as stream:
        return stream.read()


def read_bytes(path):
    with open(path, "rb") as stream:
        return stream.read()


def write_text(path, value):
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    with io.open(path, "w", encoding="utf-8") as stream:
        stream.write(value)


def read_csv(path):
    stream = open(path, "rb") if sys.version_info[0] == 2 else io.open(
        path, encoding="utf-8", newline="")
    with stream:
        reader = csv.reader(stream, delimiter=str(";"))
        records = [[cell.decode("utf-8") if isinstance(cell, bytes) else cell for cell in row]
                   for row in reader]
    return records[0], [dict(zip(records[0], row)) for row in records[1:]]
