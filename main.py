import argparse
import json
import time
from pathlib import Path

import wikitextparser as wtp
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://yugipedia.com/api.php"
CATEGORY = "Category:Duel Monsters cards"
OUT_DIR = Path("data/raw/duel_monsters_cards")
EMAIL_KEY = "USER_AGENT_EMAIL"

# Used as both a mapping and a filter; sets that do not appear as keys will not
# be added to the output.
SET_FIELDS = {
    "en_sets": "en",
    "na_sets": "na",
    "jp_sets": "jp",
}

# Yugipedia asks for a descriptive User-Agent with contact info, and at most one
# request per second.
USER_AGENT = "yugioh-collection-tracker/0.1 (contact: " + os.getenv(EMAIL_KEY) + ")"
DELAY_SECONDS = 1.0

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
# a page's data across several responses, so the paging loop below would also
# need to merge responses until the API reports "batchcomplete". The simple
# loop in its current state does not do that.
BASE_PARAMS = {
    "action": "query",
    "format": "json",
    "formatversion": "2",
    "redirects": "true",
    "generator": "categorymembers",
    "gcmtitle": CATEGORY,           # what we're filtering by
    "gcmlimit": "50",               # pages per request
    "prop": "revisions|info",       # properties to report from each page
    "rvprop": "content",            # props to include in the revisions prop
    "inprop": "url",                # extra optional fields to include in info prop
}


def fetch_pages(session, max_requests=None):
    """Yield every page in the category, following the API's paging tokens."""
    params = dict(BASE_PARAMS)
    requests_made = 0
    while True:
        response = session.get(API_URL, params=params, timeout=60)
        response.raise_for_status()
        data = response.json()
        requests_made += 1

        if "warnings" in data:
            print("API warnings:", json.dumps(data["warnings"], indent=2))
        print(f"request {requests_made}: {len(data['query']['pages'])} pages")

        yield from data["query"]["pages"]

        if "continue" not in data:
            break
        if max_requests and requests_made >= max_requests:
            break
        params.update(data["continue"])
        time.sleep(DELAY_SECONDS)


def save_page(page):
    wikitext_fields = parse_card_table_2(page["revisions"][0]["content"])
    if wikitext_fields is None:
        print("Could not parse Card Table 2 for page " + page["pageid"])
        return
    printings = []
    for field_name, region in SET_FIELDS.items():
        if field_name in wikitext_fields:
            printings.extend(parse_sets(wikitext_fields[field_name], region))
    record = {
        "pageid": page["pageid"],
        "title": page["title"],
        "url": page["canonicalurl"],
        "name_ja": wikitext_fields.get("ja_name"),
        "password": wikitext_fields.get("password"),
        "konami_id": wikitext_fields.get("database_id"),
        "card_type": wikitext_fields.get("card_type", "Monster"),
        "images": parse_images(wikitext_fields["image"]) if "image" in wikitext_fields else [],
        "printings": printings,
    }
    path = OUT_DIR / f"{page['pageid']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_card_table_2(wikitext):
    """Return the CardTable2 template's fields as a {name: value} dict."""
    parsed = wtp.parse(wikitext)
    for template in parsed.templates:
        if template.name.strip() == "CardTable2":
            return {arg.name.strip(): arg.value.strip() for arg in template.arguments}
    return None


def parse_images(image_field):
    """Turn the image field into a list of rows.

    Each line looks like: index; card image file; art-only file (optional)
    A page with a single image may instead just be one filename with no semicolons.
    """
    if ";" not in image_field:
        return [{"index": "1", "card_image": image_field, "art_image": None}]
    rows = []
    for line in image_field.splitlines():
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 2:
            continue
        rows.append(
            {
                "index": parts[0],
                "card_image": parts[1] or None,
                "art_image": (parts[2] if len(parts) > 2 else "") or None,
            }
        )
    return rows


def parse_sets(value, region):
    """Turn a *_sets field into a list of printings.

    Each line is formatted as: set number; set name; rarity, rarity
    However, for Series 1 cards (and some other exceptions), set number may be absent
    """
    printings = []
    for line in value.splitlines():
        if ";" not in line:
            continue
        parts = [part.strip() for part in line.split(";")]
        rarity_text = parts[2] if len(parts) > 2 else ""
        printings.append(
            {
                "region": region,
                "set_number": parts[0] or None,
                "set_name": parts[1] if len(parts) > 1 else None,
                "rarities": [r.strip() for r in rarity_text.split(",") if r.strip()],
            }
        )
    return printings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="stop after this many API requests (each returns up to 50 pages)",
    )
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    saved = 0
    for page in fetch_pages(session, args.max_requests):
        save_page(page)
        saved += 1
    print(f"done: saved {saved} pages to {OUT_DIR}")


if __name__ == "__main__":
    main()