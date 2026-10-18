import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

from fetch_set_util import discover_categories, fetch_tree_pages
from mediawiki_util import make_session, query_pages
from parse_card_util import parse_card_table_2, get_printings, get_images
from parse_set_util import parse_set_page, SetParseError

CATEGORY = "Category:Duel Monsters cards"
SET_ROOTS = ["Category:TCG sets", "Category:OCG sets"]
RAW_OUT_DIR = Path("data/raw")
CARD_OUT_DIR = RAW_OUT_DIR / f"duel_monsters_cards"
SET_OUT_DIR = RAW_OUT_DIR / "sets"
SET_CATEGORIES_FILE = RAW_OUT_DIR / "set_categories.json"

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


def fetch_and_save_cards(session, max_requests):
    saved = 0
    for page in query_pages(session, BASE_PARAMS, max_requests):
        save_card_page(page)
        saved += 1
    print(f"done: saved {saved} cards to {CARD_OUT_DIR}")


def save_set_page(set_page):
    path = SET_OUT_DIR / f"{set_page['page_id']}-{set_page['region']}.json"
    path.write_text(json.dumps(set_page, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_and_save_sets(session, max_requests):
    tree = discover_categories(session, SET_ROOTS)
    SET_CATEGORIES_FILE.write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"discovered {len(tree)} set categories (tree saved to {SET_CATEGORIES_FILE})")

    all_records = 0
    problems = defaultdict(list)
    for page in fetch_tree_pages(session, tree, max_requests):
        try: 
            records = parse_set_page({
                "pageid": page["pageid"],
                "title": page["title"],
                "wikitext": page["revisions"][0]["content"],
            })
        except SetParseError as e:
            problems[e.reason].append(f"{page['title']} [{e}]" if str(e) else page['title'])
            continue
        except Exception as e:  # anything unexpected shouldn't kill the run or vanish
            problems["unexpected"].append(f"{page['title']}: {type(e).__name__}: {e}")
            continue

        for record in records:
            save_set_page(record)
        all_records += len(records)

    print(f"parsed {all_records} set records")
    for reason, titles in sorted(problems.items()):
        print(f"{reason} ({len(titles)}): {titles}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="stop after this many API requests (each returns up to 50 pages); "
             "for sets, applies to each category separately",
    )
    parser.add_argument(
        "--only",
        choices=["cards", "sets"],
        help="fetch just one of the two (default: both)",
    )
    args = parser.parse_args()

    session = make_session()
    RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.only in (None, "cards"):
        shutil.rmtree(CARD_OUT_DIR, ignore_errors=True)
        CARD_OUT_DIR.mkdir(parents=True)
        fetch_and_save_cards(session, args.max_requests)

    if args.only in (None, "sets"):
        shutil.rmtree(SET_OUT_DIR, ignore_errors=True)
        SET_OUT_DIR.mkdir(parents=True)
        fetch_and_save_sets(session, args.max_requests)


if __name__ == "__main__":
    main()
