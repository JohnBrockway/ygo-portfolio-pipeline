import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

from failures import Failures
from fetch_set_util import discover_categories, fetch_tree_pages
from mediawiki_util import make_session, query_pages
from parse_card_util import parse_card_table_2, get_printings, get_images
from parse_set_util import parse_set_page, EDITION_FIELDS

CARD_CATEGORY = "Category:Duel Monsters cards"
SET_ROOTS = ["Category:Sets"]
EXCLUDED_SET_CATEGORIES = ["Category:Set information pages"]
RAW_OUT_DIR = Path(__file__).resolve().parent / "../data/raw"
CARD_OUT_DIR = RAW_OUT_DIR / "duel_monsters_cards"
SET_OUT_DIR = RAW_OUT_DIR / "sets"
SET_CATEGORIES_FILE = RAW_OUT_DIR / "set_categories.json"
KNOWN_ERRORS_FILE = Path(__file__).resolve().parent / "../known_set_errors.json"
EDITION_OVERRIDES_FILE = Path(__file__).resolve().parent / "../edition_overrides.json"

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


def fetch_and_save_cards(session, max_requests, failures):
    saved = 0
    for page in query_pages(session, CARD_QUERY_PARAMS, max_requests):
        record = build_card_record(page)
        if record is None:
            failures.add("card_page_unparseable", pageid=page['pageid'])
            continue
        write_json_to_file(CARD_OUT_DIR / f"{record['pageid']}.json", record)
        saved += 1
    print(f"Saved {saved} cards to {CARD_OUT_DIR}")


def load_known_errors(path=KNOWN_ERRORS_FILE):
    """Set of (page_id, title, reason) for sets we've already reviewed and accepted as unparseable."""
    if not path.exists():
        return set()
    with open(path, encoding="utf-8") as f:
        return {(entry["page_id"], entry["title"], entry["reason"]) for entry in json.load(f)}


def load_edition_overrides(path=EDITION_OVERRIDES_FILE):
    """{(page_id, title, region): editions} from the curated JSON, validated and in canonical order."""
    if not path.exists():
        return {}
    edition_importance_order = [slug for slug, _ in EDITION_FIELDS]
    overrides = {}
    with open(path, encoding="utf-8") as file:
        for entry in json.load(file):
            key = (entry["page_id"], entry["title"], entry["region"])
            if key in overrides or not entry["editions"] or not set(entry["editions"]) <= set(edition_importance_order):
                raise ValueError(f"Bad or duplicate edition override: {entry}")
            overrides[key] = sorted(set(entry["editions"]), key=edition_importance_order.index)
    return overrides


def apply_edition_overrides(records, overrides, failures):
    """Returns records with manual edition overrides filled in if the page listed none.

    Reports what needs attention: records still without editions, overrides whose page now lists
    editions of its own, and (only if report_unmatched, i.e. this was a full run) overrides that
    matched no record. Needs the whole run's records; neither argument is modified.
    """
    matched, resolved = set(), []
    for record in records:
        key = (record["page_id"], record["title"], record["region"])
        override = overrides.get(key)
        if override is not None:
            matched.add(key)
            if record["editions"] is None:
                record = {**record, "editions": override}
            else:
                failures.add(
                    "edition_override_page_has_edition",
                    page_id=record["page_id"],
                    title=record["title"],
                    region=record["region"],
                    comment=f"page now lists {record['editions']}; override says {override}")
        if record["editions"] is None:
            failures.add("no_editions", page_id=record["page_id"], title=record["title"], region=record["region"])
            continue
        resolved.append(record)
    for page_id, title, region in sorted(overrides.keys() - matched):
        failures.add("stale_edition_override", page_id=page_id, title=title, region=region,
                     comment="matched no record")
    return resolved


def fetch_and_save_sets(session, max_requests, failures, edition_overrides):
    tree = discover_categories(session, SET_ROOTS, EXCLUDED_SET_CATEGORIES)
    write_json_to_file(SET_CATEGORIES_FILE, tree)
    print(f"Discovered {len(tree)} set categories (tree saved to {SET_CATEGORIES_FILE})")

    records = []
    for page in fetch_tree_pages(session, tree, max_requests):
        records.extend(parse_set_page(page, failures))

    records = apply_edition_overrides(records, edition_overrides, failures)
    for record in records:
        write_json_to_file(SET_OUT_DIR / f"{record['page_id']}-{record['region']}.json", record)

    print(f"Saved {len(records)} set records")


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

    card_failures = Failures()
    set_failures = Failures(load_known_errors())
    edition_overrides = load_edition_overrides()
    session = make_session()
    RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if args.only in (None, "cards"):
        reset_dir(CARD_OUT_DIR)
        fetch_and_save_cards(session, args.max_requests, card_failures)

    if args.only in (None, "sets"):
        reset_dir(SET_OUT_DIR)
        fetch_and_save_sets(session, args.max_requests, set_failures, edition_overrides)

    card_failures.write_jsonl(RAW_OUT_DIR / "card_failures.jsonl")
    set_failures.write_jsonl(RAW_OUT_DIR / "set_failures.jsonl")


if __name__ == "__main__":
    main()
