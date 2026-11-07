#!/usr/bin/env python3
"""
main.py - fetch cards, sets and their images from Yugipedia.

Run from the project root.

Steps (--steps takes one or more, or "all"; they always run in this order, regardless of command line order):
  cards        one JSON file per card page, one folder per game:    -> <raw-out-dir>/duel_monsters_cards
                                                                    -> <raw-out-dir>/rush_duel_cards
               (see CARD_CATEGORIES; each record says which game it is from)
  sets         one JSON file per set and region     -> <raw-out-dir>/sets (+ set_categories.json)
  set_images   a WebP image per set image                           -> <raw-out-dir>/set_images (+ set_image_index.json)
  card_images  a WebP image per card image                          -> <raw-out-dir>/card_images (+ card_image_index.json)
               (the image steps are slow but resumable: files already downloaded are skipped;
               they read the set / card files the earlier steps saved, so those must exist
               from this run or an earlier one. The index files say which wiki file names have
               an image, and are rewritten at the end of every image run, even a short one.)

Inputs (required by the step named, but each may be an empty list):
  known_card_errors.json  (cards step) card pages already reviewed and accepted as unparseable
  known_set_errors.json   (sets step) sets already reviewed and accepted as unparseable
  edition_overrides.json  (sets step) curated editions for set pages that list none

Outputs (in --raw-out-dir):
  <step>_failures.jsonl   one line per failure/warning for that step, so running one step
                          never overwrites another step's file
  fetch.log               full log of the last run (overwritten each run)

Usage:
  python data_fetch/main.py --raw-out-dir data/raw --steps all
  python data_fetch/main.py --raw-out-dir data/raw --steps cards sets
  python data_fetch/main.py --raw-out-dir data/raw --steps set_images
  python data_fetch/main.py --raw-out-dir data/raw --steps card_images
"""
import argparse
import logging
from itertools import chain
from pathlib import Path

from failures import Failures
from fetch_card_util import CARD_CATEGORIES, fetch_card_records
from load_inputs import (
    iter_saved_card_records,
    iter_saved_set_records,
    load_edition_overrides,
    load_known_errors,
)
from orchestrate import fetch_card_images, fetch_set_images, fetch_set_records
from mediawiki_util import make_session
from raw_output_writer import write_card_records, write_set_categories, write_set_records

log = logging.getLogger("fetch")

STEPS = ("cards", "sets", "set_images", "card_images")  # also the order they run in
KNOWN_CARD_ERRORS_FILE = Path("data_fetch/known_card_errors.json")
KNOWN_SET_ERRORS_FILE = Path("data_fetch/known_set_errors.json")
EDITION_OVERRIDES_FILE = Path("data_fetch/edition_overrides.json")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-out-dir", required=True,
                        help="folder the raw card, set and image files are written to (created if needed)")
    parser.add_argument(
        "--steps", nargs="+", required=True, choices=[*STEPS, "all"], metavar="STEP",
        help="steps to run: cards, sets, set_images, card_images, or all. They always run in "
             "that order, because the image steps read the files the cards and sets steps save",
    )
    return parser.parse_args()


def setup_logging(log_path):
    """Milestones on the console; timestamped copy of everything, including per-request detail, in the log file."""
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(console_handler)

    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(file_handler)

    # These log every HTTP request and every PNG chunk at DEBUG, which would drown the file.
    for noisy in ("urllib3", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def save_failures(failures, path):
    failures.write_jsonl(path)
    log.info("failure counts: %s", dict(failures.counts.most_common()))
    log.info("see %s", path)


def main():
    args = parse_args()
    steps = set(STEPS) if "all" in args.steps else set(args.steps)
    run_cards = "cards" in steps
    run_sets = "sets" in steps
    run_set_images = "set_images" in steps
    run_card_images = "card_images" in steps

    raw_dir = Path(args.raw_out_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    log_path = raw_dir / "fetch.log"
    setup_logging(log_path)

    set_dir = raw_dir / "sets"
    set_categories_file = raw_dir / "set_categories.json"
    set_image_dir = raw_dir / "set_images"
    set_image_index_file = raw_dir / "set_image_index.json"
    card_image_dir = raw_dir / "card_images"
    card_image_index_file = raw_dir / "card_image_index.json"

    # Required inputs are loaded up front, so a missing file fails before any fetching starts.
    if run_cards:
        card_failures = Failures(load_known_errors(KNOWN_CARD_ERRORS_FILE))
    if run_sets:
        set_failures = Failures(load_known_errors(KNOWN_SET_ERRORS_FILE))
        edition_overrides = load_edition_overrides(EDITION_OVERRIDES_FILE)

    session = make_session()

    if run_cards:
        for source in CARD_CATEGORIES:
            log.info("Fetching cards: %s", source["category"])
            cards = fetch_card_records(session, source["category"], source["game"], card_failures)
            write_card_records(raw_dir / (source["game"] + "_cards"), cards)
        save_failures(card_failures, raw_dir / "card_failures.jsonl")

    if run_sets:
        set_records, category_tree = fetch_set_records(session, set_failures, edition_overrides)
        write_set_categories(set_categories_file, category_tree)
        write_set_records(set_dir, set_records)
        save_failures(set_failures, raw_dir / "set_failures.jsonl")

    if run_set_images:
        set_image_failures = Failures()
        # Read from disk, so this works the same after a sets step in this run or an earlier run.
        saved_set_records = iter_saved_set_records(set_dir)
        try:
            fetch_set_images(session, saved_set_records, set_image_dir, set_image_index_file, set_image_failures)
        finally:
            # Also written if the run aborts (e.g. too many failed downloads in a row).
            save_failures(set_image_failures, raw_dir / "set_image_failures.jsonl")

    if run_card_images:
        card_image_failures = Failures()
        # One stream of records across every game's folder. Chaining like this makes 
        # each folder's existence check run here, before any fetching starts.
        saved_card_records = chain.from_iterable(
            [iter_saved_card_records(raw_dir / (source["game"] + "_cards")) for source in CARD_CATEGORIES]
        )
        try:
            fetch_card_images(session, saved_card_records, card_image_dir, card_image_index_file,
                              card_image_failures)
        finally:
            save_failures(card_image_failures, raw_dir / "card_image_failures.jsonl")

    log.info("DONE; full log in %s", log_path)


if __name__ == "__main__":
    main()