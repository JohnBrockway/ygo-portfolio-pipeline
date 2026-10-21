"""Turning a card's raw printings into master printing records.

Two steps:
  1. resolve_card_printings: match each raw printing to a set record (one result per rarity).
  2. build_printing_records: give every resolved printing its final set number and id.
"""
from collections import defaultdict

from text_utils import compact_uppercase, slugify

# ------------------------------------------------------------------ step 1: resolve


def resolve_card_printings(card_id, card_title, raw_printings, set_index, failures):
    """Match a card's raw printings to set records.

    Returns "resolved printings": dicts with card_id, card_title, set (the set record),
    set_number (None if the printing has none) and rarity (None if it has none).
    Printings whose set can't be found are logged as failures and left out.
    """
    resolved = []

    for raw in raw_printings:
        region = raw.get("region")
        set_name = raw.get("set_name")
        set_number = (raw.get("set_number") or "").strip() or None

        # What gets logged if anything goes wrong with this printing.
        description = {"card_id": card_id, "card": card_title, "region": region,
                       "set_name": set_name, "set_number": set_number}

        if not set_name or not region:
            failures.add("printing_missing_set_name_or_region", **description)
            continue

        lookup = set_index.find(set_name, region)
        if lookup.set_record is None:
            failures.add(lookup.failure_kind, **description, **lookup.failure_details)
            continue

        rarities = raw.get("rarities")
        if not rarities:
            failures.add("printing_without_rarity", **description)
            rarities = [None]

        for rarity in rarities:
            resolved.append({
                "card_id": card_id,
                "card_title": card_title,
                "set": lookup.set_record,
                "set_number": set_number,
                "rarity": rarity,
            })

    return resolved


# ------------------------------------------------------------------ step 2: final records


def synthetic_number_positions(resolved_printings):
    """For printings with no set number: each card's position within its set.

    Within each set, the cards that have no number are sorted alphabetically by title
    and numbered from 1. Returns {set_id: {card_id: position}}.
    """
    cards_by_set = defaultdict(set)
    for printing in resolved_printings:
        if printing["set_number"] is None:
            sort_key = printing["card_title"].casefold()
            cards_by_set[printing["set"]["set_id"]].add((sort_key, printing["card_id"]))

    positions = {}
    for set_id, cards in cards_by_set.items():
        positions[set_id] = {}
        for position, (_, card_id) in enumerate(sorted(cards), start=1):
            positions[set_id][card_id] = position
    return positions


def make_set_number(printing, positions):
    """Returns (set_number, is_synthetic). Numberless printings get e.g. "VOL1--003"."""
    if printing["set_number"] is not None:
        return printing["set_number"], False

    set_record = printing["set"]
    prefix = set_record.get("prefix") or compact_uppercase(set_record["title"])
    position = positions[set_record["set_id"]][printing["card_id"]]
    return f"{prefix}--{position:03d}", True


def make_printing_id(printing, set_number, is_synthetic):
    """card : set : number : rarity.

    Synthetic numbers are left out of the id (replaced by "nonum") so the id
    stays stable if the alphabetical ordering shifts later.
    """
    number_part = "nonum" if is_synthetic else set_number.replace("/", "_")
    rarity_part = slugify(printing["rarity"]) if printing["rarity"] else "none"
    return f"{printing['card_id']}:{printing['set']['set_id']}:{number_part}:{rarity_part}"


def build_printing_records(resolved_printings, failures):
    """The final printing records, sorted by printing_id. Duplicate ids are logged and skipped."""
    positions = synthetic_number_positions(resolved_printings)
    records = []
    seen_ids = set()

    for printing in resolved_printings:
        set_record = printing["set"]
        set_number, is_synthetic = make_set_number(printing, positions)
        printing_id = make_printing_id(printing, set_number, is_synthetic)

        if printing_id in seen_ids:
            failures.add("duplicate_printing", printing_id=printing_id, card=printing["card_title"],
                         set=set_record["title"], set_number=set_number, rarity=printing["rarity"])
            continue
        seen_ids.add(printing_id)

        records.append({
            "printing_id": printing_id,
            "card_id": printing["card_id"],
            "set_id": set_record["set_id"],
            "set_number": set_number,
            "set_number_synthetic": is_synthetic,
            "rarity": printing["rarity"],
        })

    return sorted(records, key=lambda record: record["printing_id"])