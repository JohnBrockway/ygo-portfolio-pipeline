"""Collects every failure/warning from the build."""
import json
import logging
from collections import Counter

log = logging.getLogger(__name__)


class Failures:
    """Keeps every failure in memory and writes them all to failures.jsonl.
    
    Pass in a list of known errors (params must include page_id and title) to silently ignore them.
    """

    def __init__(self, ignored=None):
        self.records = []
        self.counts = Counter()
        self.ignored = set(ignored) if ignored else set()
        self.ignored_this_run = set()

    def add(self, kind, **details):
        key = (details.get("page_id"), details.get("title"), kind)
        if key in self.ignored:
            self.ignored_this_run.add(key)
        else:
            self.counts[kind] += 1
            self.records.append({"kind": kind, **details})

    def write_jsonl(self, path):
        """One JSON object per line, one line per occurrence."""
        with open(path, "w", encoding="utf-8") as file:
            for record in self.records:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
            for page_id, title, reason in sorted(self.ignored - self.ignored_this_run):
                stale_record = {
                    "kind": "stale_known_error",
                    "page_id": page_id,
                    "title": title,
                    "expected_reason": reason
                }
                file.write(json.dumps(stale_record, ensure_ascii=False) + "\n")