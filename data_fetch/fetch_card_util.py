"""
Fetch loop for card pages: the card categories to fetch, the parsing of one page into the
JSON record the rest of the pipeline reads, and a generator over every parsable card in one
category.
"""
from mediawiki_util import query_category_pages
from parse_card_util import parse_card_table_2, get_printings, get_images, get_card_type

# One entry per wiki category of cards. Every card found in a category is tagged with that
# category's "game" (a fixed set of values the master build and the app can rely on), and
# its records are saved in <raw-out-dir>/<folder>.
CARD_CATEGORIES = [
    {"category": "Category:Duel Monsters cards", "game": "duel_monsters", "folder": "duel_monsters_cards"},
    {"category": "Category:Rush Duel cards", "game": "rush_duel", "folder": "rush_duel_cards"},
    {"category": "Category:Monster Tokens", "game": "duel_monsters", "folder": "monster_token_cards"},
]

# FALLBACK, kept for posterity: if matching set pages by the set names in the
# wikitext runs into trouble, add "linkshere" to "prop" for the card fetch (a card-only copy
# of CATEGORY_PAGES_PARAMS in mediawiki_util) plus
#   "lhlimit": "max", "lhprop": "pageid|title|redirect",
#   "lhnamespace": "0|3006|3024",   # set pages, "Set Card Lists:", "Set Card Galleries:"
# Set pages link to every card they contain, so each card's linkshere list
# holds its sets' page IDs. It is the heaviest property, hence the namespace filter.
# NOTE: any list property (linkshere, categories, links...) makes the API split
# a page's data across several responses, so the paging loop in
# mediawiki_util.query() would also need to merge responses until the API
# reports "batchcomplete". The simple loop there does not do that.

def verify_numeral(string):
    """
    Returns string if it's a string representation of a number with ASCII numerals, otherwise None
    """
    value = (string or "").strip()
    if value.isascii() and value.isdigit():
        return value
    return None


def build_card_record(card_page, game, failures):
    """
    Turn a raw card page into a JSON record to save, or None if it's not parsable with
    the expected template.

    Problems with individual image rows are reported to failures; the rest of the
    record is still returned.
    """
    revisions = card_page.get("revisions")
    if not revisions:
        return None
    card_fields = parse_card_table_2(revisions[0]["slots"]["main"]["content"])
    if card_fields is None:
        return None

    password = verify_numeral(card_fields.get("password"))
    konami_id = verify_numeral(card_fields.get("database_id"))

    return {
        "pageid": card_page["pageid"],
        "title": card_page["title"],
        "url": card_page["canonicalurl"],
        "game": game,
        "name_ja": card_fields.get("ja_name"),
        "password": password,
        "konami_id": konami_id,
        "card_type": get_card_type(card_fields),
        "images": get_images(card_fields.get("image"), failures, card_page["pageid"], card_page["title"]),
        "printings": get_printings(card_fields),
    }


def fetch_card_records(session, category, game, failures):
    """Yield one record per parsable card page in the category; pages that can't be parsed go to failures."""
    for page in query_category_pages(session, category):
        record = build_card_record(page, game, failures)
        if record is None:
            failures.add("card_page_unparseable", page_id=page["pageid"], title=page.get("title"))
            continue
        yield record