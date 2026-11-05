"""Reading the raw card/set JSON files and the curated lists (known errors, card id overrides)."""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

def find_json_files(path):
    """A single file, or every .json file under a directory (recursively)."""
    path = Path(path)
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.json"))


def load_records(path, record_type, failures):
    """Load every record (a dict) from the JSON files at `path`.

    Each file may hold one record or a list of records.
    Unreadable files and non-dict records are logged as failures and skipped.
    """
    files = find_json_files(path)
    records = []

    for file in files:
        try:
            content = json.loads(file.read_text(encoding="utf-8"))
        except Exception as error:
            failures.add("unreadable_file", record_type=record_type, file=str(file), error=repr(error))
            continue

        items = content if isinstance(content, list) else [content]
        for item in items:
            if isinstance(item, dict):
                records.append(item)
            else:
                failures.add("malformed_record", record_type=record_type,
                             file=file.name, got=type(item).__name__)

    log.info("loaded %d %s records from %d files", len(records), record_type, len(files))
    return records


def load_known_errors(path):
    """Failures we've already reviewed and accepted, as a list of fingerprint dicts.

    The file is a list of objects, each a failure line from failures.jsonl cut down to the
    fields that identify it, e.g. {"kind": "empty_set", "set_id": "1001672-jp", "title": "Some Set Page"}.
    "comment" is a free-text note and is dropped. A missing file just means no known errors.
    An entry that isn't an object, has no "kind", has nothing but "kind" (it would silence a
    whole kind of failure), or repeats another entry raises ValueError, since that is a
    mistake in the file itself.
    """
    if not path or not Path(path).exists():
        return []

    entries = json.loads(Path(path).read_text(encoding="utf-8"))

    known_errors = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: expected an object, got {entry!r}")
        fingerprint = {field: value for field, value in entry.items() if field != "comment"}
        if "kind" not in fingerprint or len(fingerprint) < 2:
            raise ValueError(f'{path}: expected "kind" plus at least one more field, got {entry!r}')
        if fingerprint in known_errors:
            raise ValueError(f"{path}: duplicate known error {entry!r}")
        known_errors.append(fingerprint)
    return known_errors

def load_card_id_overrides(path):
    """Load the manual card id overrides, keyed by wiki pageid."""
    if not path or not Path(path).exists():
        return {}

    entries = json.loads(Path(path).read_text(encoding="utf-8"))

    overrides = {}
    for entry in entries:
        pageid = entry["pageid"]
        if pageid in overrides:
            raise ValueError(f"Two card id overrides for pageid {pageid}")
        overrides[pageid] = entry

    return overrides

def load_image_index(path):
    """{wiki file name: thumbnail file name} written by the fetch step's image steps.

    The file must exist (an empty object is fine).
    """
    with open(path, encoding="utf-8") as file:
        return json.load(file)