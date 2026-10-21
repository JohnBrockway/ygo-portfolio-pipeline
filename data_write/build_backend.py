#!/usr/bin/env python3
"""
build_backend.py - join card printings to set records and write the master dataset.

Inputs (JSON files, one record per file or a list per file; searched recursively):
  --cards-dir   card records  (pageid, title, konami_id, password, printings[...], images[...])
  --sets-dir    set records   (page_id, title, region, name, names, image, prefix, release_date ...)
  --expected-empty  optional JSON: [{"set_id": "1001672-jp", "title": "Set Page Title"}, ...]. Sets
                    we already know have no printings. set_id and title must both match exactly. A
                    set with no printings is only flagged (unexpected_empty_set) if it is NOT listed here.


Outputs (in --out-dir):
  cards.json, sets.json, printings.json   the master data (flat, normalized)
  manifest.json                           counts + sha256 per file (cache-busting for clients)
  failures.jsonl                          one line per failure/warning, every occurrence
  build.log                               full log

Usage:
  python build_master.py --cards-dir data/raw/duel_monsters_cards --sets-dir data/raw/sets --out-dir out [--pretty]
"""
import argparse
import logging
from pathlib import Path

from failures import Failures
from data_join_orchestrate import build_master_data
from output_writer import write_master_files
from record_loading import load_expected_empty, load_records

log = logging.getLogger("build_master")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cards-dir", required=True)
    parser.add_argument("--sets-dir", required=True)
    parser.add_argument("--out-dir", default="out")
    parser.add_argument("--expected-empty", default="expected_empty_sets.json")
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

    failures = Failures()
    card_records = load_records(args.cards_dir, "card", failures)
    set_records = load_records(args.sets_dir, "set", failures)
    expected_empty = load_expected_empty(args.expected_empty)

    master = build_master_data(card_records, set_records, expected_empty, failures)
    counts = write_master_files(out_dir, master, failures, pretty=args.pretty)

    log.info("DONE %s", counts)
    log.info("failure counts: %s", dict(failures.counts.most_common()))
    log.info("see %s", out_dir / "failures.jsonl")


if __name__ == "__main__":
    main()