#!/usr/bin/env python3
"""
main.py - join card printings to set records and write the master dataset.

Inputs (JSON files, one record per file or a list per file; searched recursively):
  --cards-dir   one or more folders of card records, one folder per game
                (page_id, title, game, konami_id, password, printings[...], images[...])
  --sets-dir    set records   (page_id, title, region, name, names, image, prefix, release_date ...)
  --card-image-index  JSON written by the fetch card_images step: {wiki file name: image file name}
  --set-image-index   JSON written by the fetch set_images step, same shape
                    Images with no entry get a null "file" (cards) or "image" (sets) in the
                    master data (and are reported).

Curated files (fixed paths, read relative to where the script is run; no command-line
options). Each must exist, but an empty list [] is fine:
  data_write/card_id_overrides.json       manual card ids for cards whose natural id collides,
                                          keyed by wiki page_id
  data_write/known_build_errors.json      failures already reviewed and accepted, so they are not
                                          logged; the entry format is described in failures.py
  data_write/printing_overrides.json      which artwork a printing shows; the entry format is
                                          described in printing_overrides.py
  data_write/set_aliases.json             manual set-name aliases


Outputs (in --out-dir):
  cards.json, sets.json, printings.json   the master data (normalized; a setcode lists its printings)
  cards/, sets/                           only the images that cards.json / sets.json reference,
                                          copied from the fetch folders (stale files removed)
  manifest.json                           counts + sha256 per file (cache-busting for clients)
  failures.jsonl                          one line per failure/warning, every occurrence
  build.log                               full log

Usage (run from the project root):
  python data_write/main.py --cards-dir data/duel_monsters_cards data/rush_duel_cards \
      --sets-dir data/sets \
      --card-image-index data/card_image_index.json --set-image-index data/set_image_index.json \
      --card-images-dir data/card_images --set-images-dir data/set_images \
      --out-dir out [--pretty]
"""
import argparse
import logging
import sys
from pathlib import Path

# If run as `python data_write/main.py`, only data_write/ is on the import path by default.
# Adding the project root makes the data_write package and its neighbour common/ importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.failures import Failures
from data_write.image_output import copy_used_images
from data_write.orchestrate import build_master_data
from data_write.output_writer import write_master_files
from data_write.record_loading import (load_card_id_overrides, load_image_index,
                                       load_known_errors, load_printing_overrides,
                                       load_records, load_set_aliases)

log = logging.getLogger("build_master")

CARD_ID_OVERRIDES_FILE = Path("data_write/card_id_overrides.json")
KNOWN_BUILD_ERRORS_FILE = Path("data_write/known_build_errors.json")
PRINTING_OVERRIDES_FILE = Path("data_write/printing_overrides.json")
SET_ALIASES_FILE = Path("data_write/set_aliases.json")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cards-dir", required=True, nargs="+",
                        help="one or more folders of card records, e.g. one per game")
    parser.add_argument("--sets-dir", required=True)
    parser.add_argument("--card-image-index", required=True)
    parser.add_argument("--set-image-index", required=True)
    parser.add_argument("--card-images-dir", required=True,
                        help="folder of card images written by the fetch card_images step")
    parser.add_argument("--set-images-dir", required=True,
                        help="folder of set images written by the fetch set_images step")
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
    card_records = []
    for cards_dir in args.cards_dir:
        card_records += load_records(cards_dir, "card", failures)
    set_records = load_records(args.sets_dir, "set", failures)
    card_id_overrides = load_card_id_overrides(CARD_ID_OVERRIDES_FILE)
    printing_overrides = load_printing_overrides(PRINTING_OVERRIDES_FILE)
    set_aliases = load_set_aliases(SET_ALIASES_FILE)
    card_image_index = load_image_index(args.card_image_index)
    set_image_index = load_image_index(args.set_image_index)

    master = build_master_data(card_records, set_records, set_aliases, card_id_overrides,
                               printing_overrides, card_image_index, set_image_index, failures)
    image_counts = copy_used_images(master, args.card_images_dir, args.set_images_dir, out_dir, failures)
    counts = write_master_files(out_dir, master, failures, pretty=args.pretty)

    log.info("DONE %s", counts)
    log.info("images %s", image_counts)
    log.info("failure counts: %s", dict(failures.counts.most_common()))
    log.info("see %s", out_dir / "failures.jsonl")


if __name__ == "__main__":
    main()