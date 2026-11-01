#!/usr/bin/env python3
"""
fetch_and_parse.py - fetch cards, sets and set images from Yugipedia into data/raw.

Steps (--only picks one; the default runs cards and sets):
  cards    one JSON file per card page          -> data/raw/duel_monsters_cards
  sets     one JSON file per set and region     -> data/raw/sets (+ set_categories.json)
  images   a WebP thumbnail per set image       -> data/raw/set_images
           (slow, resumable, and needs the sets fetched first, so it only runs when asked for)

Each step writes its own <step>_failures.jsonl next to its output, so running one step never
overwrites another step's file.

Usage:
  python fetch_and_parse.py [--only cards|sets|images] [--max-requests N]
"""
import argparse
from pathlib import Path

from failures import Failures
from fetch_card_util import fetch_card_records
from load_inputs import load_edition_overrides, load_known_errors, load_saved_set_records
from orchestrate import fetch_set_images, fetch_set_records
from mediawiki_util import make_session
from raw_output_writer import write_card_records, write_set_categories, write_set_records

RAW_OUT_DIR = Path(__file__).resolve().parent / "../data/raw"
CARD_OUT_DIR = RAW_OUT_DIR / "duel_monsters_cards"
SET_OUT_DIR = RAW_OUT_DIR / "sets"
SET_CATEGORIES_FILE = RAW_OUT_DIR / "set_categories.json"
IMAGE_OUT_DIR = RAW_OUT_DIR / "set_images"
KNOWN_ERRORS_FILE = Path(__file__).resolve().parent / "../known_set_errors.json"
EDITION_OVERRIDES_FILE = Path(__file__).resolve().parent / "../edition_overrides.json"


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="stop after this many API requests (each returns up to 50 pages); "
             "for sets, applies to each category separately; "
             "for images, applies to batches of 50 images",
    )
    parser.add_argument(
        "--only",
        choices=["cards", "sets", "images"],
        help="fetch just one of the three (default: cards and sets; images are slow and "
             "need the sets fetched first, so they only run when asked for)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    RAW_OUT_DIR.mkdir(parents=True, exist_ok=True)
    session = make_session()

    if args.only in (None, "cards"):
        card_failures = Failures()
        cards = fetch_card_records(session, args.max_requests, card_failures)
        write_card_records(CARD_OUT_DIR, cards)
        card_failures.write_jsonl(RAW_OUT_DIR / "card_failures.jsonl")

    if args.only in (None, "sets"):
        set_failures = Failures(load_known_errors(KNOWN_ERRORS_FILE))
        edition_overrides = load_edition_overrides(EDITION_OVERRIDES_FILE)
        set_records, category_tree = fetch_set_records(session, args.max_requests, set_failures, edition_overrides)
        write_set_categories(SET_CATEGORIES_FILE, category_tree)
        write_set_records(SET_OUT_DIR, set_records)
        set_failures.write_jsonl(RAW_OUT_DIR / "set_failures.jsonl")

    if args.only == "images":
        image_failures = Failures()
        set_records = load_saved_set_records(SET_OUT_DIR)
        try:
            fetch_set_images(session, set_records, IMAGE_OUT_DIR, args.max_requests, image_failures)
        finally:
            # Also written if the run aborts (e.g. too many failed downloads in a row).
            image_failures.write_jsonl(RAW_OUT_DIR / "image_failures.jsonl")


if __name__ == "__main__":
    main()
