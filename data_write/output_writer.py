"""Writing the master data files and the manifest."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1


def write_json(path, data, pretty=False):
    """Write `data` as JSON. Returns the file's size and sha256 (for the manifest)."""
    if pretty:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    content = text.encode("utf-8")
    Path(path).write_bytes(content)
    return {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def write_master_files(out_dir, master, failures, pretty=False):
    """Write cards/sets/printings.json, manifest.json and failures.jsonl. Returns the counts."""
    out_dir = Path(out_dir)

    files = {
        "cards.json": write_json(out_dir / "cards.json", master.cards, pretty),
        "sets.json": write_json(out_dir / "sets.json", master.sets, pretty),
        "printings.json": write_json(out_dir / "printings.json", master.printings, pretty),
    }
    counts = {
        "cards": len(master.cards),
        "sets": len(master.sets),
        "printings": len(master.printings),
    }

    # The manifest lets clients cache-bust: each file's hash changes when its content does.
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "counts": counts,
        "files": files,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    write_json(out_dir / "manifest.json", manifest, pretty)

    failures.write_jsonl(out_dir / "failures.jsonl")
    return counts