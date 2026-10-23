"""Joins cards, printings and sets into the master dataset."""
from collections import namedtuple

from cards import build_card_record, choose_card_id
from printings import build_printing_records, resolve_card_printings
from set_index import SetIndex
from set_pruning import build_set_records

MasterData = namedtuple("MasterData", ["cards", "sets", "printings"])


def collect_cards(card_records, set_index, known_duplicate_cards, failures):
    """Build the card records and resolve every card's printings against the set index.
 
    Returns (cards_by_id, resolved_printings).
    """
    cards_by_id = {}
    resolved_printings = []
    seen_duplicate_pageids = set()
    applied_overrides = {}  # pageid -> the id the card would have had without the override

    for card in card_records:
        title = card.get("title")
        pageid = card.get("pageid")

        override = known_duplicate_cards.get(pageid)
        if override is not None:
            seen_duplicate_pageids.add(pageid)
            if override["title"] != title:
                failures.add("card_id_override_mismatch", pageid=pageid, title=title,
                             expected_title=override["title"])
                override = None  # don't apply it; the natural id will likely collide and fail loudly

        natural_id = choose_card_id(card)

        if override is not None:
            card_id = override["card_id"]
            applied_overrides[pageid] = natural_id
        else:
            card_id = natural_id

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
 
    report_stale_overrides(known_duplicate_cards, seen_duplicate_pageids,
                           applied_overrides, cards_by_id, failures)
 
    return cards_by_id, resolved_printings

def report_stale_overrides(known_duplicate_cards, seen_duplicate_pageids,
                           applied_overrides, cards_by_id, failures):
    """Flag overrides that matched no page, or that are no longer needed."""
    for pageid, override in known_duplicate_cards.items():
        if pageid not in seen_duplicate_pageids:
            failures.add("unused_card_id_override", pageid=pageid, title=override["title"])

    for pageid, natural_id in applied_overrides.items():
        if natural_id is None:
            continue  # card has no natural id at all, so the override is still doing real work

        holder = cards_by_id.get(natural_id)
        natural_id_is_free = holder is None or holder["pageid"] == pageid
        if natural_id_is_free:
            failures.add("unneeded_card_id_override", pageid=pageid,
                         title=known_duplicate_cards[pageid]["title"], natural_id=natural_id)


def build_master_data(card_records, set_records, expected_empty, known_duplicate_cards, failures):
    set_index = SetIndex(set_records, failures)
    cards_by_id, resolved_printings = collect_cards(card_records, set_index, known_duplicate_cards, failures)
    printings = build_printing_records(resolved_printings, failures)
    sets = build_set_records(set_index, printings, expected_empty, failures)

    set_index.report_unused_aliases(failures)

    cards = sorted(cards_by_id.values(), key=lambda card: card["card_id"])
    return MasterData(cards=cards, sets=sets, printings=printings)