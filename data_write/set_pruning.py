"""Building the final set list: only sets that have printings are kept."""
from collections import Counter


def is_expected_empty(set_record, expected_empty):
    """True if the set's (set_id, title) pair is on the expected-empty list.

    Both must match exactly, so a set that merely shares a title or an id
    with a listed one is still flagged.
    """
    return (set_record["set_id"], set_record["title"]) in expected_empty


def build_set_records(set_index, printings, expected_empty, failures):
    """Final set records, sorted by set_id.

    Sets with no printings are dropped. A dropped set that isn't on the
    expected-empty list is logged as a failure so new ones get noticed.
    """
    printing_counts = Counter(printing["set_id"] for printing in printings)
    set_records = []

    for set_id, set_record in sorted(set_index.sets_by_id.items()):
        if printing_counts[set_id] == 0:
            if not is_expected_empty(set_record, expected_empty):
                failures.add("unexpected_empty_set", set_id=set_id,
                             title=set_record["title"], region=set_record["region"])
            continue

        set_records.append({
            "set_id": set_id,
            "page_id": set_record.get("page_id"),
            "title": set_record["title"],
            "region": set_record["region"],
            "name": set_record.get("name"),
            "names": set_record.get("names"),
            "image": set_record.get("image"),
            "prefix": set_record.get("prefix"),
            "postfix": set_record.get("postfix"),
            "release_date": set_record.get("release_date"),
            "printing_count": printing_counts[set_id],
        })

    return set_records