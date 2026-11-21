"""Reading the raw card/set JSON files and the curated lists (known errors, card id overrides)."""
import json
import logging
from pathlib import Path

from failures import KNOWN_ERROR_NOTE_FIELDS

log = logging.getLogger(__name__)


def find_json_files(path):
    """A single file, or every .json file under a directory (recursively)."""
    path = Path(path)
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.json"))


def read_json(path):
    """The parsed contents of one JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_json_objects(path):
    """The entries of a JSON file that holds a list of objects.

    Raises ValueError if an entry isn't an object, since that is a mistake in the file itself.
    """
    entries = read_json(path)
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: expected an object, got {entry!r}")
    return entries


def load_records(path, record_type, failures):
    """Load every record (a dict) from the JSON files at `path`.

    Each file may hold one record or a list of records.
    Unreadable files and non-dict records are logged as failures and skipped.
    """
    files = find_json_files(path)
    records = []

    for file in files:
        try:
            content = read_json(file)
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
    "comment" is a free-text note and is dropped.
    The file must exist (an empty list is fine), so a wrong path can't silently
    drop every known error.
    An entry that isn't an object, has no "kind", has nothing but "kind" (it would silence a
    whole kind of failure), or repeats another entry raises ValueError, since that is a
    mistake in the file itself.
    """
    entries = read_json_objects(path)

    known_errors = []
    for entry in entries:
        fingerprint = {field: value for field, value in entry.items()
                       if field not in KNOWN_ERROR_NOTE_FIELDS}
        if "kind" not in fingerprint or len(fingerprint) < 2:
            raise ValueError(f'{path}: expected "kind" plus at least one more field, got {entry!r}')
        if fingerprint in known_errors:
            raise ValueError(f"{path}: duplicate known error {entry!r}")
        known_errors.append(fingerprint)
    return known_errors


def load_card_id_overrides(path):
    """Load the manual card id overrides, keyed by wiki page_id.

    The file must exist (an empty list is fine), so a wrong path can't silently
    drop every override.
    """
    entries = read_json_objects(path)

    overrides = {}
    for entry in entries:
        page_id = entry["page_id"]
        if page_id in overrides:
            raise ValueError(f"Two card id overrides for page_id {page_id}")
        overrides[page_id] = entry

    return overrides


def load_printing_overrides(path):
    """Load the manual printing overrides (which artwork a printing shows) as a list of entries.

    The file is a list of objects; see printing_overrides.py for their fields.
    The file must exist (an empty list is fine), so a wrong path can't silently
    drop every override. An entry that isn't an object raises ValueError,
    since that is a mistake in the file itself.
    """
    return read_json_objects(path)


def load_set_aliases(path):
    """Load the manual set-name aliases.

    The file must exist (an empty list is fine), so a wrong path can't silently
    drop every alias.
    The file is a JSON list of {"region", "alias", "target_set_id", "note"?} entries.
    SetIndex checks each entry and logs the bad ones.
    """
    return read_json(path)


def load_image_index(path):
    """{wiki file name: image file name} written by the fetch step's image steps.

    The file must exist (an empty object is fine).
    """
    return read_json(path)