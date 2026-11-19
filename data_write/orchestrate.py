"""Joins cards, printings and sets into the master dataset."""
from collections import namedtuple

from cards import build_card_record, choose_card_id
from printing_overrides import apply_printing_overrides
from printings import build_printing_records, resolve_card_printings
from set_index import SetIndex
from set_pruning import build_set_records

MasterData = namedtuple("MasterData", ["cards", "sets", "printings"])


def collect_cards(card_records, set_index, known_duplicate_cards, card_image_index, failures):
    """Build the card records and resolve every card's printings against the set index.

    Returns (cards_by_id, resolved_printings).
    """
    cards_by_id = {}
    resolved_printings = []
    seen_duplicate_page_ids = set()
    applied_overrides = {}  # page_id -> the id the card would have had without the override

    for card in card_records:
        title = card.get("title")
        page_id = card.get("page_id")

        override = known_duplicate_cards.get(page_id)
        if override is not None:
            seen_duplicate_page_ids.add(page_id)
            if override["title"] != title:
                failures.add("card_id_override_mismatch", page_id=page_id, title=title,
                             expected_title=override["title"])
                override = None  # don't apply it; the natural id will likely collide and fail loudly

        natural_id = choose_card_id(card)

        if override is not None:
            card_id = override["card_id"]
            applied_overrides[page_id] = natural_id
        else:
            card_id = natural_id

        if card_id is None:
            failures.add("missing_card_id", title=title)
            continue

        raw_printings = card.get("printings")
        if not raw_printings:
            failures.add("card_without_printings", card_id=card_id, title=title)
            continue

        card_printings = resolve_card_printings(card_id, title, raw_printings, set_index, failures)
        if not card_printings:
            failures.add("card_without_resolved_printings", card_id=card_id, title=title)
            continue

        if card_id in cards_by_id:
            failures.add("duplicate_card_id", card_id=card_id, title=title,
                         other_title=cards_by_id[card_id]["title"])
            continue

        cards_by_id[card_id] = build_card_record(card_id, card, card_image_index, failures)
        resolved_printings += card_printings

    report_stale_overrides(known_duplicate_cards, seen_duplicate_page_ids,
                           applied_overrides, cards_by_id, failures)

    return cards_by_id, resolved_printings


def report_stale_overrides(known_duplicate_cards, seen_duplicate_page_ids,
                           applied_overrides, cards_by_id, failures):
    """Flag overrides that matched no page, or that are no longer needed."""
    for page_id, override in known_duplicate_cards.items():
        if page_id not in seen_duplicate_page_ids:
            failures.add("unused_card_id_override", page_id=page_id, title=override["title"])

    for page_id, natural_id in applied_overrides.items():
        if natural_id is None:
            continue  # card has no natural id at all, so the override is still doing real work

        holder = cards_by_id.get(natural_id)
        natural_id_is_free = holder is None or holder["page_id"] == page_id
        if natural_id_is_free:
            failures.add("unneeded_card_id_override", page_id=page_id,
                         title=known_duplicate_cards[page_id]["title"], natural_id=natural_id)


def collect_card_images(cards_by_id):
    """{card_id: {image index: image file name or None}}, for checking printing overrides."""
    card_images = {}
    for card_id, card in cards_by_id.items():
        card_images[card_id] = {image["index"]: image["file"] for image in card["images"]}
    return card_images


def build_master_data(card_records, set_records, known_duplicate_cards, printing_overrides,
                      card_image_index, set_image_index, failures):
    set_index = SetIndex(set_records, failures)
    cards_by_id, resolved_printings = collect_cards(card_records, set_index, known_duplicate_cards,
                                                    card_image_index, failures)
    printings = build_printing_records(resolved_printings, failures)
    apply_printing_overrides(printings, printing_overrides, collect_card_images(cards_by_id), failures)
    sets = build_set_records(set_index, printings, cards_by_id, set_image_index, failures)

    set_index.report_unused_aliases(failures)

    cards = sorted(cards_by_id.values(), key=lambda card: card["card_id"])
    return MasterData(cards=cards, sets=sets, printings=printings)