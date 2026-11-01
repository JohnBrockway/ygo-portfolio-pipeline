"""Writes the raw fetch results to disk: one JSON file per card or set record."""
import json
import logging
import shutil

from progress import Progress

log = logging.getLogger(__name__)


def write_json_to_file(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def reset_dir(path):
    """Delete the directory if it exists, then recreate it empty."""
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)


def write_card_records(out_dir, records):
    """Replace out_dir's contents with one file per card record; returns how many were written."""
    reset_dir(out_dir)
    saved = 0
    progress = Progress(log)  # records stream in from the fetch, so this is the cards step's heartbeat
    for record in records:
        write_json_to_file(out_dir / f"{record['pageid']}.json", record)
        saved += 1
        progress.update("Cards saved so far: %d", saved)
    log.info("Saved %d cards to %s", saved, out_dir)
    return saved


def write_set_records(out_dir, records):
    """Replace out_dir's contents with one file per set record; returns how many were written."""
    reset_dir(out_dir)
    saved = 0
    for record in records:
        write_json_to_file(out_dir / f"{record['page_id']}-{record['region']}.json", record)
        saved += 1
    log.info("Saved %d set records to %s", saved, out_dir)
    return saved


def write_set_categories(path, tree):
    write_json_to_file(path, tree)
    log.info("Set category tree saved to %s", path)