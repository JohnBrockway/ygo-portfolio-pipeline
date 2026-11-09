"""Manual printing overrides.

Yugipedia doesn't say which artwork a printing shows, so that is entered by hand
(in the app's edit mode), exported to printing_overrides.json and applied here
after the setcode records are built.

Each entry looks like:
    {"setcode_id": "k19964:1020970-jp:RD_KP16-JP016", "rarity": "Super Rare",
     "variant": 2, "artwork": "2", "image": "SomeCard-XXX-JP-SR.png.webp", "label": null}

  variant 1  is the printing the build already made for that rarity: the override
             sets its artwork and label and marks it verified.
  variant 2+ are extra versions of that printing (another artwork, a stamp, ...)
             that the override creates.
  artwork    is the card image index, exactly as in cards.json (a string).
  image      is the image file at that index when the override was made (optional).
             If the card's image at that index is now a different file, the indexes
             have probably shifted, so the entry is rejected.
  label      is free text that tells versions apart, e.g. "Dueling Network stamp" (optional).

Bad entries are logged as failures and skipped.
"""
from printings import FIRST_VARIANT, make_printing, sort_printings


def find_printing(setcode_record, rarity, variant):
    for printing in setcode_record["printings"]:
        if printing["rarity"] == rarity and printing["variant"] == variant:
            return printing
    return None


def apply_printing_overrides(setcode_records, overrides, card_images, failures):
    """Applies the overrides to the setcode records, changing them in place.

    card_images is {card_id: {image index: image file name or None}}.
    """
    records_by_id = {record["setcode_id"]: record for record in setcode_records}
    claimed_variants = set()
    claimed_looks = set()
    changed_setcode_ids = set()

    for entry in overrides:
        setcode_id = entry.get("setcode_id")
        rarity = entry.get("rarity")
        variant = entry.get("variant")
        artwork = entry.get("artwork")
        image = entry.get("image")
        label = (entry.get("label") or "").strip() or None

        # What gets logged if anything goes wrong with this entry.
        description = {
            "setcode_id": setcode_id,
            "rarity": rarity,
            "variant": variant,
            "artwork": artwork,
        }

        record = records_by_id.get(setcode_id)
        if record is None:
            failures.add("override_setcode_not_found", **description)
            continue

        if type(variant) is not int or variant < FIRST_VARIANT:
            failures.add("override_invalid_variant", **description)
            continue

        if (setcode_id, rarity, variant) in claimed_variants:
            failures.add("override_duplicate", **description)
            continue

        base_printing = find_printing(record, rarity, FIRST_VARIANT)
        if base_printing is None:
            failures.add("override_rarity_not_found", **description)
            continue

        image_files = card_images.get(record["card_id"], {})
        if type(artwork) is not str or artwork not in image_files:
            failures.add("override_artwork_not_on_card", **description, card_id=record["card_id"])
            continue

        if image is not None and image != image_files[artwork]:
            failures.add("override_image_changed", **description,
                         expected_image=image, current_image=image_files[artwork])
            continue

        # Two versions of a rarity with the same artwork need different labels.
        look = (setcode_id, rarity, artwork, label)
        if look in claimed_looks:
            failures.add("override_indistinguishable", **description, label=label)
            continue

        if variant == FIRST_VARIANT:
            printing = base_printing
        else:
            printing = make_printing(setcode_id, rarity, variant)
            record["printings"].append(printing)

        printing["artwork"] = artwork
        printing["label"] = label
        printing["verified"] = True

        claimed_variants.add((setcode_id, rarity, variant))
        claimed_looks.add(look)
        changed_setcode_ids.add(setcode_id)

    for setcode_id in changed_setcode_ids:
        sort_printings(records_by_id[setcode_id]["printings"])