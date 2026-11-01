"""
Composes the fetch steps: pulls raw pages from the wiki and turns them into the records
that get written to disk. Cards have no composition to do (see fetch_card_util), so this
holds the set fetch and the image step.

The set fetch returns its records without writing anything. The image step is the one
exception: it downloads straight into its folder, because it is slow and resumable (a
rerun only fetches what's missing).
"""
import logging

from fetch_image_util import download_images, local_image_name, output_name
from fetch_set_util import discover_categories, fetch_tree_pages
from parse_set_util import parse_set_page

log = logging.getLogger(__name__)

SET_ROOTS = ["Category:Sets"]
EXCLUDED_SET_CATEGORIES = ["Category:Set information pages"]


def apply_edition_overrides(records, overrides, failures):
    """Returns records with manual edition overrides filled in if the page listed none.

    Reports what needs attention: records still without editions, overrides whose page now lists
    editions of its own, and overrides that matched no record. Needs the whole run's records;
    neither argument is modified.
    """
    matched, resolved = set(), []
    for record in records:
        key = (record["page_id"], record["title"], record["region"])
        override = overrides.get(key)
        if override is not None:
            matched.add(key)
            if record["editions"] is None:
                record = {**record, "editions": override}
            else:
                failures.add(
                    "edition_override_page_has_edition",
                    page_id=record["page_id"],
                    title=record["title"],
                    region=record["region"],
                    comment=f"page now lists {record['editions']}; override says {override}")
        if record["editions"] is None:
            failures.add("no_editions", page_id=record["page_id"], title=record["title"], region=record["region"])
            continue
        resolved.append(record)
    for page_id, title, region in sorted(overrides.keys() - matched):
        failures.add("stale_edition_override", page_id=page_id, title=title, region=region,
                     comment="matched no record")
    return resolved


def fetch_set_records(session, max_requests, failures, edition_overrides):
    """Fetch and parse every set page. Returns (records, category_tree)."""
    log.info("Discovering set categories")
    tree = discover_categories(session, SET_ROOTS, EXCLUDED_SET_CATEGORIES)
    log.info("Discovered %d set categories", len(tree))

    records = []
    for page in fetch_tree_pages(session, tree, max_requests):
        records.extend(parse_set_page(page, failures))

    return apply_edition_overrides(records, edition_overrides, failures), tree


def collect_set_image_names(set_records, failures):
    """Unique image names referenced by the set records.

    Records with no usable image are reported to failures (keyed by the set's page and region).
    """
    names = set()
    for record in set_records:
        raw = record.get("image")
        name = local_image_name(raw)
        if name is not None:
            names.add(name)
        elif (raw or "").strip():
            failures.add("set_image_name_unusable", page_id=record["page_id"], title=record["title"],
                         region=record["region"], comment=f"image field: {raw!r}")
        else:
            failures.add("set_has_no_image", page_id=record["page_id"], title=record["title"],
                         region=record["region"])
    log.info("%d distinct set images referenced", len(names))
    return sorted(names)


def fetch_set_images(session, set_records, image_dir, max_requests, failures):
    # Deliberately NOT reset_dir(): downloads are slow, so a rerun only fetches what's missing
    # (delete to force a refetch).
    image_dir.mkdir(parents=True, exist_ok=True)
    names = collect_set_image_names(set_records, failures)
    todo = [name for name in names if not (image_dir / output_name(name)).exists()]
    log.info("%d already downloaded, %d to fetch", len(names) - len(todo), len(todo))

    saved = download_images(session, todo, image_dir, failures, max_requests)
    log.info("Saved %d images to %s", saved, image_dir)