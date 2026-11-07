"""
Resolve and download wiki images (set and card) so they can be served from owned storage
(hotlinking was running into CORP and 429 errors from the wiki API).

  1. resolve_image_urls(): one API request per 50 files, asking for the URL of each
     File: page's image.
  2. download_images(): fetch each original (one throttled request each), shrink it
     to fit MAX_IMAGE_SIZE as a WebP with Pillow, and save only the WebP.
  3. write_image_index(): record which wiki file names have an image on disk, and what
     it's called. The master build reads this instead of repeating the naming rule.
"""
import io
import json
import logging
import math
import re

import requests
from PIL import Image

from mediawiki_util import download, query

log = logging.getLogger(__name__)

BATCH_SIZE = 50                 # titles per API request
MAX_IMAGE_SIZE = (360, 480)     # max width, max height in px
WEBP_QUALITY = 80
MAX_CONSECUTIVE_FAILURES = 5    # stop instead of hammering a host that is refusing us


def local_image_name(wiki_name):
    """The wiki file name without any File: prefix, spaces as underscores.

    Returns None for empty or unsafe values.
    """
    name = re.sub(r"^(file|image):", "", (wiki_name or "").strip(), flags=re.IGNORECASE)
    name = name.replace(" ", "_")
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    return name


def output_name(name):
    """File name an image is saved under."""
    return f"{name}.webp"


def resolve_image_urls(session, names, failures):
    """{name: original image URL or None} for up to BATCH_SIZE local image names.

    Names that don't resolve map to None and are reported to `failures` with the reason.
    """
    params = {
        "titles": "|".join(f"File:{name}" for name in names),
        "redirects": "true",
        "prop": "imageinfo",
        "iiprop": "url|mime",
    }
    moves = {}            # title -> title it was normalized / redirected to
    pages_by_title = {}
    for data in query(session, params):
        result = data.get("query", {})
        for move in result.get("normalized", []) + result.get("redirects", []):
            moves[move["from"]] = move["to"]
        for page in result.get("pages", []):
            pages_by_title[page["title"]] = page

    urls = {}
    for name in names:
        title = f"File:{name}"
        for _ in range(3):  # normalization, then a redirect (or two)
            title = moves.get(title, title)
        page = pages_by_title.get(title)
        info = page.get("imageinfo") if page else None
        if info:
            urls[name] = info[0].get("url")
            continue

        urls[name] = None
        if page is None:
            failures.add("image_not_in_response", title=name)
        elif page.get("invalid"):
            failures.add("image_invalid_title", title=name, comment=page.get("invalidreason", ""))
        elif page.get("missing"):
            failures.add("image_file_missing", title=name)
        else:
            failures.add("image_no_imageinfo", title=name)
    return urls


def shrink_to_webp(data):
    """Original image bytes -> WebP image bytes, shrunk to fit MAX_IMAGE_SIZE."""
    with Image.open(io.BytesIO(data)) as image:
        if image.mode not in ("RGB", "RGBA"):
            # Palette and grayscale images: keep transparency if there is any.
            has_alpha = "transparency" in image.info or "A" in image.mode
            image = image.convert("RGBA" if has_alpha else "RGB")
        image.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, "WEBP", quality=WEBP_QUALITY, method=6)
        return out.getvalue()


def download_images(session, names, out_dir, failures):
    """Download images for names into out_dir; returns how many were saved."""
    saved = 0
    consecutive_failures = 0
    total_batches = math.ceil(len(names) / BATCH_SIZE)

    for batch_number, start in enumerate(range(0, len(names), BATCH_SIZE), start=1):
        batch = names[start:start + BATCH_SIZE]
        urls = resolve_image_urls(session, batch, failures)
        valid_urls_count = sum(url is not None for url in urls.values())
        # One line per batch (about a minute apart) doubles as the progress heartbeat.
        log.info("Batch %d/%d: %d/%d resolved, %d images saved so far",
                 batch_number, total_batches, valid_urls_count, len(batch), saved)

        for name in batch:
            url = urls[name]
            if url is None:
                continue  # failure already reported by resolve_image_urls
            try:
                data, content_type = download(session, url)
            except (requests.RequestException, RuntimeError) as error:
                failures.add("image_download_failed", title=name, comment=str(error))
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    raise RuntimeError(
                        f"{consecutive_failures} downloads in a row failed (rate limited?); "
                        "finished files are kept, rerun later to continue"
                    )
                continue
            consecutive_failures = 0

            if not content_type.startswith("image/"):
                failures.add("image_not_an_image", title=name, comment=content_type)
                continue
            try:
                webp_data = shrink_to_webp(data)
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                # e.g. SVGs or corrupt files; the tile falls back to its placeholder
                failures.add("image_unreadable", title=name, comment=f"{content_type}: {error}")
                continue

            # Write then rename so an interrupted run never leaves a truncated file behind.
            path = out_dir / output_name(name)
            partial = path.with_name(path.name + ".part")
            try:
                partial.write_bytes(webp_data)
                partial.replace(path)
            except OSError as error:
                # e.g. a file name this OS can't store; don't lose a multi-hour run over it
                failures.add("image_save_failed", title=name, comment=str(error))
                continue
            saved += 1

    return saved


def write_image_index(index_path, names_by_wiki_name, image_dir):
    """Write {wiki file name: image file name} for every name whose image is on disk.

    names_by_wiki_name maps each wiki file name as the records spell it to its local name.
    Names without an image are left out, which is how the master build knows they have none.
    """
    index = {}
    for wiki_name, name in names_by_wiki_name.items():
        image_name = output_name(name)
        if (image_dir / image_name).exists():
            index[wiki_name] = image_name
    with open(index_path, "w", encoding="utf-8") as file:
        json.dump(index, file, ensure_ascii=False, indent=1, sort_keys=True)
    log.info("Wrote %d of %d image names to %s", len(index), len(names_by_wiki_name), index_path)