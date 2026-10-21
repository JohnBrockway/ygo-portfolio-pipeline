"""Building the final set list: only sets that have printings are kept."""
from collections import Counter


def build_set_records(set_index, printings, failures):
    """Final set records, sorted by set_id.

    Sets with no printings are dropped.
    """
    printing_counts = Counter(printing["set_id"] for printing in printings)
    set_records = []

    for set_id, set_record in sorted(set_index.sets_by_id.items()):
        if printing_counts[set_id] == 0:
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