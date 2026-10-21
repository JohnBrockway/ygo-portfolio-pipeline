"""Collects every failure/warning from the build."""
import json
import logging
from collections import Counter

log = logging.getLogger(__name__)


class Failures:
    """Keeps every failure in memory and writes them all to failures.jsonl."""

    def __init__(self):
        self.records = []
        self.counts = Counter()

    def add(self, kind, **details):
        self.counts[kind] += 1
        self.records.append({"kind": kind, **details})

    def write_jsonl(self, path):
        """One JSON object per line, one line per occurrence."""
        with open(path, "w", encoding="utf-8") as file:
            for record in self.records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")