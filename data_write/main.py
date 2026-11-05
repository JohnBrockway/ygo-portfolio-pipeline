#!/usr/bin/env python3
"""
build_backend.py - join card printings to set records and write the master dataset.

Inputs (JSON files, one record per file or a list per file; searched recursively):
  --cards-dir   one or more folders of card records, one folder per game
                (pageid, title, game, konami_id, password, printings[...], images[...])
  --sets-dir    set records   (page_id, title, region, name, names, image, prefix, release_date ...)
  --card-image-index  JSON written by the fetch card_images step: {wiki file name: thumbnail file name}
  --set-image-index   JSON written by the fetch set_images step, same shape
                    Images with no entry get no "thumb" field in the master data (and are reported).
  --known-errors    JSON list of failures already reviewed and accepted, so they are not logged
                    (a missing file means none are known). Each entry is a failure line from
                    failures.jsonl cut down to the fields that identify it, always including "kind",
                    e.g. {"kind": "empty_set", "set_id": "1001672-jp", "title": "Set Page Title"}.
                    A failure matches an entry when it has every one of the entry's fields with the
                    same value, so list enough fields to pin down exactly the failure you reviewed.
                    "comment" is a free-text note and is never matched. An entry that matches nothing
                    in a run is reported as stale_known_error, so it can be removed.



Outputs (in --out-dir):
  cards.json, sets.json, printings.json   the master data (flat, normalized)
  manifest.json                           counts + sha256 per file (cache-busting for clients)
  failures.jsonl                          one line per failure/warning, every occurrence
  build.log                               full log

Usage:
  python main.py --cards-dir data/duel_monsters_cards data/rush_duel_cards \
      --sets-dir data/sets \
      --card-image-index data/card_image_index.json --set-image-index data/set_image_index.json \
      --out-dir out [--pretty]
"""
import argparse
import logging
from itertools import chain
from pathlib import Path

from failures import Failures
from orchestrate import build_master_data
from output_writer import write_master_files
from record_loading import load_image_index, load_known_errors, load_records, load_card_id_overrides

log = logging.getLogger("build_master")

KNOWN_BUILD_ERRORS_FILE = Path("data_write/known_build_errors.json")
KNOWN_DUPLICATE_CARDS_FILE = Path("data_write/known_duplicate_cards.json")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cards-dir", required=True, nargs="+",
                        help="one or more folders of card records, e.g. one per game")
    parser.add_argument("--sets-dir", required=True)
    parser.add_argument("--card-image-index", required=True)
    parser.add_argument("--set-image-index", required=True)
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--pretty", action="store_true",
                        help="indent JSON (dev only; bigger files)")
    return parser.parse_args()


def setup_logging(out_dir):
    """Short messages on the console; timestamped copy of everything in build.log."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
    root.addHandler(console_handler)

    file_handler = logging.FileHandler(out_dir / "build.log", mode="w", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root.addHandler(file_handler)


def main():
    args = parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(out_dir)

    failures = Failures(load_known_errors(KNOWN_BUILD_ERRORS_FILE))
    # Every folder's records in one list; each record says which game it belongs to.
    card_records = list(chain.from_iterable(
        load_records(cards_dir, "card", failures) for cards_dir in args.cards_dir
    ))
    set_records = load_records(args.sets_dir, "set", failures)
    known_duplicate_cards = load_card_id_overrides(KNOWN_DUPLICATE_CARDS_FILE)
    card_image_index = load_image_index(args.card_image_index)
    set_image_index = load_image_index(args.set_image_index)

    master = build_master_data(card_records, set_records, known_duplicate_cards,
                               card_image_index, set_image_index, failures)
    counts = write_master_files(out_dir, master, failures, pretty=args.pretty)

    log.info("DONE %s", counts)
    log.info("failure counts: %s", dict(failures.counts.most_common()))
    log.info("see %s", out_dir / "failures.jsonl")


if __name__ == "__main__":
    main()