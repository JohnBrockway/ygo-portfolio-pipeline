"""
Fetch loop for card pages: the query parameters, the parsing of one page into the JSON
record the rest of the pipeline reads, and a generator over every parsable card.
"""
from mediawiki_util import query_pages
from parse_card_util import parse_card_table_2, get_printings, get_images

CARD_CATEGORY = "Category:Duel Monsters cards"

# FALLBACK, kept for posterity: if matching set pages by the set names in the
# wikitext runs into trouble, add "linkshere" to "prop" below plus
#   "lhlimit": "max", "lhprop": "pageid|title|redirect",
#   "lhnamespace": "0|3006|3024",   # set pages, "Set Card Lists:", "Set Card Galleries:"
# Set pages link to every card they contain, so each card's linkshere list
# holds its sets' page IDs. It is the heaviest property, hence the namespace filter.
# NOTE: any list property (linkshere, categories, links...) makes the API split
# a page's data across several responses, so the paging loop in
# mediawiki_util.query() would also need to merge responses until the API
# reports "batchcomplete". The simple loop there does not do that.
CARD_QUERY_PARAMS = {
    "redirects": "true",
    "generator": "categorymembers",
    "gcmtitle": CARD_CATEGORY,      # what we're filtering by
    "gcmlimit": "50",               # pages per request
    "prop": "revisions|info",       # properties to report from each page
    "rvprop": "content",            # props to include in the revisions prop
    "rvslots": "main",              # wikitext is stored in the main slot
    "inprop": "url",                # extra optional fields to include in info prop
}


def verify_numeral(string):
    """
    Returns string if it's a string representation of a number with ASCII numerals, otherwise None
    """
    value = (string or "").strip()
    if value.isascii() and value.isdigit():
        return value
    return None


def build_card_record(card_page, failures):
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
        "name_ja": card_fields.get("ja_name"),
        "password": password,
        "konami_id": konami_id,
        "card_type": card_fields.get("card_type", "Monster"),
        "images": get_images(card_fields.get("image"), failures, card_page["pageid"], card_page["title"]),
        "printings": get_printings(card_fields),
    }


def fetch_card_records(session, failures):
    """Yield one record per parsable card page; pages that can't be parsed go to failures."""
    for page in query_pages(session, CARD_QUERY_PARAMS):
        record = build_card_record(page, failures)
        if record is None:
            failures.add("card_page_unparseable", pageid=page['pageid'])
            continue
        yield record