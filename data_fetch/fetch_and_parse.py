import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

from fetch_set_util import discover_categories, fetch_tree_pages
from mediawiki_util import make_session, query_pages
from parse_card_util import parse_card_table_2, get_printings, get_images
from parse_set_util import parse_set_page, SetParseError

CARD_CATEGORY = "Category:Duel Monsters cards"
SET_ROOTS = ["Category:Sets"]
EXCLUDED_SET_CATEGORIES = ["Category:Set information pages"]
RAW_OUT_DIR = Path(__file__).resolve().parent / "../data/raw"
CARD_OUT_DIR = RAW_OUT_DIR / "duel_monsters_cards"
SET_OUT_DIR = RAW_OUT_DIR / "sets"
SET_CATEGORIES_FILE = RAW_OUT_DIR / "set_categories.json"
KNOWN_ERRORS_FILE = Path(__file__).resolve().parent / "known_set_errors.json"

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


def write_json_to_file(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_dir(path):
    """Delete the directory if it exists, then recreate it empty."""
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)


def verify_numeral(string):
    """
    Returns string if it's a string representation of a number with ASCII numerals, otherwise None
    """
    value = (string or "").strip()
    if value.isascii() and value.isdigit():
        return value
    return None


def build_card_record(card_page):
    """
    Turn a raw card page into a JSON record to save, or None if it's not parsable with
    the expected template.
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
        "images": get_images(card_fields["image"]) if "image" in card_fields else [],
        "printings": get_printings(card_fields),
    }


def fetch_and_save_cards(session, max_requests):
    saved = 0
    skipped = 0
    for page in query_pages(session, CARD_QUERY_PARAMS, max_requests):
        record = build_card_record(page)
        if record is None:
            print(f"Could not parse page {page['pageid']}")
            skipped += 1
            continue
        write_json_to_file(CARD_OUT_DIR / f"{record['pageid']}.json", record)
        saved += 1
    print(f"done: saved {saved} cards to {CARD_OUT_DIR}. ({skipped} skipped)")


def load_known_errors(path=KNOWN_ERRORS_FILE):
    """Set of (page_id, title, reason) for sets we've already reviewed and accepted as unparseable."""
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {(entry["page_id"], entry["title"], entry["reason"]) for entry in json.load(f)}


def fetch_and_save_sets(session, max_requests):
    tree = discover_categories(session, SET_ROOTS, EXCLUDED_SET_CATEGORIES)
    write_json_to_file(SET_CATEGORIES_FILE, tree)
    print(f"discovered {len(tree)} set categories (tree saved to {SET_CATEGORIES_FILE})")

    known_errors = load_known_errors()
    known_errors_seen = set() 
    saved = 0
    problems = defaultdict(list)  # reason -> list of page titles (with detail if any)
    for page in fetch_tree_pages(session, tree, max_requests):
        try:
            records = parse_set_page(page)
        except SetParseError as e:
            key = (page["pageid"], page["title"], e.reason)
            if key in known_errors:
                known_errors_seen.add(key)
                continue
            problems[e.reason].append(f'{{"page_id": {page["pageid"]}, "title": "{page["title"]}", "reason": "{e.reason}", "comment": "{e}"}},')
            continue
        except Exception as e:  # anything unexpected shouldn't kill the run or vanish
            problems["unexpected"].append(f"{page['title']}: {type(e).__name__}: {e}")
            continue

        for record in records:
            write_json_to_file(SET_OUT_DIR / f"{record['page_id']}-{record['region']}.json", record)
        saved += len(records)

    print(f"Saved {saved} set records ({len(known_errors_seen)} known errors suppressed)")

    stale = sorted(known_errors - known_errors_seen)
    if stale:
        print(f"STALE known errors ({len(stale)}) - in {KNOWN_ERRORS_FILE} but not encountered this run:")
        for page_id, title, reason in stale:
            print(f"    {page_id} {title!r} ({reason})")

    for reason, messages in sorted(problems.items()):
        print(f"{reason} ({len(messages)}):")
        for message in messages:
            print(f"    {message}")


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
        reset_dir(CARD_OUT_DIR)
        fetch_and_save_cards(session, args.max_requests)

    if args.only in (None, "sets"):
        reset_dir(SET_OUT_DIR)
        fetch_and_save_sets(session, args.max_requests)


if __name__ == "__main__":
    main()
