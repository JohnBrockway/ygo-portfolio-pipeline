"""Collects every failure/warning from the build."""
import json
import logging
from collections import Counter

log = logging.getLogger(__name__)

# Fields allowed on a known error for humans to read; not used when matching.
KNOWN_ERROR_NOTE_FIELDS = {"comment"}


class Failures:
    """Keeps every failure in memory and writes them all to failures.jsonl.

    Pass in known errors to silently ignore failures that were already reviewed and accepted.
    A known error is a dict of fields (always including "kind") copied from the failure it
    stands for. A failure matches it when the failure has every one of those fields with the
    same value, so the fields chosen are the fingerprint: more fields, a narrower match.
    A "comment" field may be added to a known error to explain why it was accepted; it is
    ignored when matching.
    """

    def __init__(self, known_errors=None):
        self.records = []
        self.counts = Counter()
        self.known_errors = list(known_errors) if known_errors else []
        self.matched_known_errors = set()  # indexes into known_errors

    @staticmethod
    def _matches(record, known_error):
        return all(
            field in record and record[field] == value
            for field, value in known_error.items()
            if field not in KNOWN_ERROR_NOTE_FIELDS
        )

    def add(self, kind, **details):
        record = {"kind": kind, **details}

        matching_indexes = [
            index for index, known_error in enumerate(self.known_errors)
            if self._matches(record, known_error)
        ]
        if matching_indexes:
            self.matched_known_errors.update(matching_indexes)
            return

        self.counts[kind] += 1
        self.records.append(record)

    def write_jsonl(self, path):
        """One JSON object per line, one line per occurrence."""
        for index, known_error in enumerate(self.known_errors):
            if index not in self.matched_known_errors:
                self.add("stale_known_error", known_error=known_error)

        with open(path, "w", encoding="utf-8") as file:
            for record in self.records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")