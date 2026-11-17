"""Copying the images the master data uses into the output folder.

Card and set images are handled the same way: the output folder ends up holding exactly the
files that cards.json / sets.json reference, so images for pruned cards or sets, and stale
files left by earlier builds, are not shipped.
"""
import logging
import shutil
from pathlib import Path

log = logging.getLogger("build_master")


def used_card_image_files(cards):
    return {image["file"] for card in cards for image in card["images"] if image["file"]}


def used_set_image_files(sets):
    return {set_record["image"] for set_record in sets if set_record.get("image")}


def same_version(source, dest):
    """True if the copy at dest looks identical to source (same size and modified time)."""
    source_stat, dest_stat = source.stat(), dest.stat()
    return source_stat.st_size == dest_stat.st_size and source_stat.st_mtime_ns == dest_stat.st_mtime_ns


def sync_images(source_dir, dest_dir, used_files, folder_name, failures):
    """Make dest_dir hold exactly used_files, copied from source_dir. Returns the counts.

    Files already in dest_dir that look identical are left alone, so rebuilds are quick.
    Referenced files missing from source_dir are reported as failures.
    """
    source_dir, dest_dir = Path(source_dir), Path(dest_dir)
    if source_dir.resolve() == dest_dir.resolve():
        raise ValueError(f"{folder_name}: the source and output folders are the same: {source_dir}")
    dest_dir.mkdir(parents=True, exist_ok=True)

    copied = up_to_date = missing = 0
    for name in sorted(used_files):
        source = source_dir / name
        if not source.is_file():
            failures.add("image_file_missing", folder=folder_name, file=name)
            missing += 1
            continue
        dest = dest_dir / name
        if dest.is_file() and same_version(source, dest):
            up_to_date += 1
            continue
        shutil.copy2(source, dest)
        copied += 1

    removed = 0
    for path in dest_dir.iterdir():
        if path.is_file() and path.name not in used_files:
            path.unlink()
            removed += 1

    source_total = sum(1 for path in source_dir.iterdir() if path.is_file())
    counts = {
        "copied": copied,
        "up_to_date": up_to_date,
        "missing": missing,
        "removed_stale": removed,
        "left_out_unused": source_total - copied - up_to_date,
    }
    return counts


def copy_used_images(master, card_images_dir, set_images_dir, out_dir, failures):
    """Copy the images cards.json and sets.json use into <out_dir>/card_images and set_images."""
    out_dir = Path(out_dir)
    return {
        "card_images": sync_images(card_images_dir, out_dir / "cards",
                                   used_card_image_files(master.cards), "card_images", failures),
        "set_images": sync_images(set_images_dir, out_dir / "sets",
                                  used_set_image_files(master.sets), "set_images", failures),
    }