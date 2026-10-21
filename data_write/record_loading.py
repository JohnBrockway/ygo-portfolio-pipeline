"""Reading the raw card/set JSON files and the expected-empty-sets list."""
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