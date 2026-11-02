"""
Loads the files the fetch steps read: the curated JSONs (known set errors, edition
overrides) and the set and card records saved by an earlier run.
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


def iter_saved_records(records_dir, step):
    """The records an earlier run of `step` saved, in file-name order, one at a time.

    A generator rather than a list: card records in particular are large (each carries its
    full printings list) and there are over 14,000 of them. The folder is checked right
    away, not on first use.
    """
    if not records_dir.exists():
        raise SystemExit(f"{records_dir} not found; run with --steps {step} first.")
    return (json.loads(path.read_text(encoding="utf-8")) for path in sorted(records_dir.glob("*.json")))


def iter_saved_set_records(sets_dir):
    return iter_saved_records(sets_dir, "sets")


def iter_saved_card_records(cards_dir):
    return iter_saved_records(cards_dir, "cards")