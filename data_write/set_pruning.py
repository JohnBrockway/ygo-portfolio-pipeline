"""Building the final set list: only sets that have printings are kept."""
from collections import Counter


def build_set_record(set_record, printing_count, image_index, failures):
    """The master set record. `thumb` (the thumbnail's file name) is only present if one was downloaded."""
    record = {
        "set_id": set_record["set_id"],
        "page_id": set_record.get("page_id"),
        "title": set_record["title"],
        "region": set_record["region"],
        "name": set_record.get("name"),
        "names": set_record.get("names"),
        "image": set_record.get("image"),
        "prefix": set_record.get("prefix"),
        "postfix": set_record.get("postfix"),
        "release_date": set_record.get("release_date"),
        "editions": set_record["editions"],
        "printing_count": printing_count,
    }

    thumb = image_index.get(set_record.get("image"))
    if thumb is None:
        failures.add("set_image_missing_thumbnail", set_id=set_record["set_id"],
                     title=set_record["title"], region=set_record["region"])
    else:
        record["thumb"] = thumb
    return record


def build_set_records(set_index, printings, image_index, failures):
    """Final set records, sorted by set_id.

    Sets with no printings are dropped and logged as empty_set. Sets we've already
    reviewed and accepted as empty go in the known-errors file, which Failures applies;
    if such a set gains printings it stops being logged, and Failures reports its
    entry as stale.
    """
    printing_counts = Counter(printing["set_id"] for printing in printings)
    set_records = []

    for set_id, set_record in sorted(set_index.sets_by_id.items()):
        printing_count = printing_counts[set_id]

        if printing_count == 0:
            failures.add("empty_set", set_id=set_id,
                         title=set_record["title"], region=set_record["region"])
        else:
            set_records.append(build_set_record(set_record, printing_count, image_index, failures))

    return set_records