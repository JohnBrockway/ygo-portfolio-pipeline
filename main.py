import argparse
import json
import os
import shutil
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from parse_util import parse_card_table_2, get_printings, get_images

load_dotenv()

API_URL = "https://yugipedia.com/api.php"
CATEGORY = "Category:Duel Monsters cards"
OUT_DIR = Path("data/raw/duel_monsters_cards")
EMAIL_KEY = "USER_AGENT_EMAIL"

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
    wikitext_dict = parse_card_table_2(page["revisions"][0]["content"])
    if wikitext_dict is None:
        print("Could not parse Card Table 2 for page " + page["pageid"])
        return
    record = {
        "pageid": page["pageid"],
        "title": page["title"],
        "url": page["canonicalurl"],
        "name_ja": wikitext_dict.get("ja_name"),
        "password": wikitext_dict.get("password"),
        "konami_id": wikitext_dict.get("database_id"),
        "card_type": wikitext_dict.get("card_type", "Monster"),
        "images": get_images(wikitext_dict["image"]) if "image" in wikitext_dict else [],
        "printings": get_printings(wikitext_dict),
    }
    path = OUT_DIR / f"{page['pageid']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="stop after this many API requests (each returns up to 50 pages)",
    )
    args = parser.parse_args()

    shutil.rmtree(OUT_DIR)
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