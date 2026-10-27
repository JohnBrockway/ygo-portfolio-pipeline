"""Building the final set list: only sets that have printings are kept."""
from collections import Counter


def is_expected_empty(set_record, expected_empty):
    """True if the set's (set_id, title) pair is on the expected-empty list.

    Both must match exactly, so a set that merely shares a title or an id
    with a listed one is still flagged.
    """
    return (set_record["set_id"], set_record["title"]) in expected_empty


def build_set_record(set_record, printing_count):
    return {
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


def build_set_records(set_index, printings, expected_empty, failures):
    """Final set records, sorted by set_id.

    Sets with no printings are dropped. Two cases are logged so the
    expected-empty list stays accurate:
      unexpected_empty_set              no printings, but not on the expected-empty list
      expected_empty_set_has_printings  on the expected-empty list, but has printings now
                                        (the set is kept, and can come off the list)
    """
    printing_counts = Counter(printing["set_id"] for printing in printings)
    set_records = []

    for set_id, set_record in sorted(set_index.sets_by_id.items()):
        printing_count = printing_counts[set_id]
        is_listed_as_empty = is_expected_empty(set_record, expected_empty)

        if printing_count == 0 and not is_listed_as_empty:
            failures.add("unexpected_empty_set", set_id=set_id,
                         title=set_record["title"], region=set_record["region"])

        if printing_count > 0 and is_listed_as_empty:
            failures.add("expected_empty_set_has_printings", set_id=set_id,
                         title=set_record["title"], region=set_record["region"],
                         printing_count=printing_count)

        if printing_count > 0:
            set_records.append(build_set_record(set_record, printing_count))

    return set_records