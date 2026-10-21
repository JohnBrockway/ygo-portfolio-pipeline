"""Joins cards, printings and sets into the master dataset."""
from collections import namedtuple

from cards import build_card_record, choose_card_id
from printings import build_printing_records, resolve_card_printings
from set_index import SetIndex
from set_pruning import build_set_records

MasterData = namedtuple("MasterData", ["cards", "sets", "printings"])


def collect_cards(card_records, set_index, failures):
    """Build the card records and resolve every card's printings against the set index.
 
    Returns (cards_by_id, resolved_printings).
    """
    cards_by_id = {}
    resolved_printings = []
 
    for card in card_records:
        title = card.get("title")
 
        card_id = choose_card_id(card)
        if card_id is None:
            failures.add("missing_card_id", title=title)
            continue
 
        if card_id in cards_by_id:
            failures.add("duplicate_card_id", card_id=card_id, title=title,
                         other_title=cards_by_id[card_id]["title"])
            continue
 
        cards_by_id[card_id] = build_card_record(card_id, card)
 
        raw_printings = card.get("printings")
        if not raw_printings:
            failures.add("card_without_printings", card_id=card_id, title=title)
            continue
 
        resolved_printings += resolve_card_printings(card_id, title, raw_printings, set_index, failures)
 
    return cards_by_id, resolved_printings


def build_master_data(card_records, set_records, failures):
    set_index = SetIndex(set_records, failures)
    cards_by_id, resolved_printings = collect_cards(card_records, set_index, failures)
    printings = build_printing_records(resolved_printings, failures)
    sets = build_set_records(set_index, printings, failures)

    cards = sorted(cards_by_id.values(), key=lambda card: card["card_id"])
    return MasterData(cards=cards, sets=sets, printings=printings)