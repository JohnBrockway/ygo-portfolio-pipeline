"""
Loads the files the fetch steps read: the curated JSONs (known set errors, edition
overrides) and the set records saved by an earlier run.
"""
import json

from parse_set_util import EDITION_FIELDS


def load_known_errors(path):
    """Set of (page_id, title, reason) for sets we've already reviewed and accepted as unparseable.

    The file must exist (an empty list is fine).
    """
    with open(path, encoding="utf-8") as file:
        return {(entry["page_id"], entry["title"], entry["reason"]) for entry in json.load(file)}


def load_edition_overrides(path):
    """{(page_id, title, region): editions} from the curated JSON, validated and in canonical order.

    The file must exist (an empty list is fine).
    """
    edition_importance_order = [slug for slug, _ in EDITION_FIELDS]
    overrides = {}
    with open(path, encoding="utf-8") as file:
        for entry in json.load(file):
            key = (entry["page_id"], entry["title"], entry["region"])
            if key in overrides or not entry["editions"] or not set(entry["editions"]) <= set(edition_importance_order):
                raise ValueError(f"Bad or duplicate edition override: {entry}")
            overrides[key] = sorted(set(entry["editions"]), key=edition_importance_order.index)
    return overrides


def load_saved_set_records(sets_dir):
    """The set records an earlier run saved, in file-name order."""
    if not sets_dir.exists():
        raise SystemExit(f"{sets_dir} not found; run with --only sets first.")
    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(sets_dir.glob("*.json"))]