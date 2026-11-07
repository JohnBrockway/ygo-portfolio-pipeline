"""Building the final set list: only sets that have printings are kept."""
from collections import Counter, defaultdict


def find_set_games(printings, cards_by_id):
    """{set_id: sorted list of games}, from the games of the cards that have a printing in each set.

    Most sets have one game; a few (e.g. promotional campaigns) span more than one.
    """
    games_seen = defaultdict(set)
    for printing in printings:
        card = cards_by_id[printing["card_id"]]
        games_seen[printing["set_id"]].add(card["game"])

    return {set_id: sorted(games) for set_id, games in games_seen.items()}


def build_set_record(set_record, printing_count, games, image_index, failures):
    """The master set record. `image` is the image file's name in our storage, or None if we have none."""
    image = image_index.get(set_record.get("image"))
    if image is None:
        failures.add("set_image_missing", set_id=set_record["set_id"],
                     title=set_record["title"], region=set_record["region"])

    return {
        "set_id": set_record["set_id"],
        "page_id": set_record.get("page_id"),
        "title": set_record["title"],
        "region": set_record["region"],
        "games": games,
        "name": set_record.get("name"),
        "names": set_record.get("names"),
        "image": image,
        "prefix": set_record.get("prefix"),
        "postfix": set_record.get("postfix"),
        "release_date": set_record.get("release_date"),
        "editions": set_record["editions"],
        "printing_count": printing_count,
    }


def build_set_records(set_index, printings, cards_by_id, image_index, failures):
    """Final set records, sorted by set_id.

    Sets with no printings are dropped and logged as empty_set. Sets we've already
    reviewed and accepted as empty go in the known-errors file, which Failures applies;
    if such a set gains printings it stops being logged, and Failures reports its
    entry as stale.

    Each kept set gets the games of its cards (see find_set_games).
    """
    printing_counts = Counter(printing["set_id"] for printing in printings)
    games_by_set_id = find_set_games(printings, cards_by_id)
    set_records = []

    for set_id, set_record in sorted(set_index.sets_by_id.items()):
        printing_count = printing_counts[set_id]

        if printing_count == 0:
            failures.add("empty_set", set_id=set_id,
                         title=set_record["title"], region=set_record["region"])
        else:
            set_records.append(build_set_record(set_record, printing_count,
                                                games_by_set_id[set_id], image_index, failures))

    return set_records