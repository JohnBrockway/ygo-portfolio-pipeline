"""Collects every failure/warning from the build."""
import json
import logging
from collections import Counter

log = logging.getLogger(__name__)


class Failures:
    """Keeps every failure in memory and writes them all to failures.jsonl.

    Pass in known errors to silently ignore failures that were already reviewed and accepted.
    A known error is a dict of fields (always including "kind") copied from the failure it
    stands for. A failure matches it when the failure has every one of those fields with the
    same value, so the fields chosen are the fingerprint: more fields, a narrower match.
    """

    def __init__(self, known_errors=None):
        self.records = []
        self.counts = Counter()
        self.known_errors = list(known_errors) if known_errors else []
        self.matched_known_errors = set()  # indexes into known_errors

    def add(self, kind, **details):
        record = {"kind": kind, **details}

        is_known = False
        for index, known_error in enumerate(self.known_errors):
            if all(field in record and record[field] == value for field, value in known_error.items()):
                self.matched_known_errors.add(index)
                is_known = True
        if is_known:
            return

        self.counts[kind] += 1
        self.records.append(record)
        

    def write_jsonl(self, path):
        """One JSON object per line, one line per occurrence."""
        with open(path, "w", encoding="utf-8") as file:
            for record in self.records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            for index, known_error in enumerate(self.known_errors):
                    if index not in self.matched_known_errors:
                        self.add("stale_known_error", known_error=known_error)