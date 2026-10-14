import argparse
import json
import shutil
from pathlib import Path

from mediawiki_util import make_session, query_pages
from parse_card_util import parse_card_table_2, get_printings, get_images

CATEGORY = "Category:Duel Monsters cards"
RAW_OUT_DIR = Path("data/raw")
CARD_OUT_DIR = RAW_OUT_DIR / f"duel_monsters_cards"

# Yugipedia runs MediaWiki 1.31, so page text comes back directly under
# "revisions" (no "slots"; do not add rvslots).
#
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
BASE_PARAMS = {
    "redirects": "true",
    "generator": "categorymembers",
    "gcmtitle": CATEGORY,           # what we're filtering by
    "gcmlimit": "50",               # pages per request
    "prop": "revisions|info",       # properties to report from each page
    "rvprop": "content",            # props to include in the revisions prop
    "inprop": "url",                # extra optional fields to include in info prop
}


def save_card_page(card_page):
    wikitext_dict = parse_card_table_2(card_page["revisions"][0]["content"])
    if wikitext_dict is None:
        print("Could not parse Card Table 2 for page " + str(card_page["pageid"]))
        return
    record = {
        "pageid": card_page["pageid"],
        "title": card_page["title"],
        "url": card_page["canonicalurl"],
        "name_ja": wikitext_dict.get("ja_name"),
        "password": wikitext_dict.get("password"),
        "konami_id": wikitext_dict.get("database_id"),
        "card_type": wikitext_dict.get("card_type", "Monster"),
        "images": get_images(wikitext_dict["image"]) if "image" in wikitext_dict else [],
        "printings": get_printings(wikitext_dict),
    }
    path = CARD_OUT_DIR / f"{card_page['pageid']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_cards(session, max_requests):
    saved = 0
    for page in query_pages(session, BASE_PARAMS, max_requests):
        save_card_page(page)
        saved += 1
    print(f"done: saved {saved} cards to {CARD_OUT_DIR}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="stop after this many API requests (each returns up to 50 pages); "
             "for sets, applies to each category separately",
    )
    args = parser.parse_args()

    session = make_session()
    RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(CARD_OUT_DIR, ignore_errors=True)
    CARD_OUT_DIR.mkdir(parents=True)
    fetch_cards(session, args.max_requests)


if __name__ == "__main__":
    main()