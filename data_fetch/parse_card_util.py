import re

from regions import WHITELISTED_REGIONS

import wikitextparser as wtp

COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

SPECIFIC_MONSTER_TYPES = ["Pendulum", "Synchro", "Ritual", "Xyz", "Fusion", "Link"]


def parse_card_table_2(wikitext):
    """Return the CardTable2 template's fields as a {name: value} dict, or None if the page doesn't have that template."""
    parsed = wtp.parse(COMMENT_RE.sub("", wikitext))
    for template in parsed.templates:
        if template.name.strip().lower() == "cardtable2":
            return {arg.name.strip(): arg.value.strip() for arg in template.arguments}
    return None


def split_fields(line, count):
    """Split a `;`-separated line into exactly `count` stripped fields.

    Missing trailing fields become empty strings; extra fields are dropped.
    """
    parts = [part.strip() for part in line.split(";")]
    parts += [""] * (count - len(parts))
    return parts[:count]


def get_printings(card_fields):
    """All printings for the card, across the whitelisted regions."""
    printings = []
    for region in sorted(WHITELISTED_REGIONS):
        field_name = f"{region}_sets"
        if field_name in card_fields:
            printings.extend(parse_sets_for_region(card_fields[field_name], region))
    return printings


def parse_sets_for_region(sets_field, region):
    """Turn a *_sets field into a list of printings.

    Each line is formatted as: set number; set name; rarity, rarity
    However, for Series 1 cards (and some other exceptions), set number may be absent
    """
    printings = []
    for line in sets_field.splitlines():
        if ";" not in line:
            continue
        set_number, set_name, rarity_text = split_fields(line, 3)
        printings.append(
            {
                "region": region,
                "set_number": set_number or None,
                "set_name": set_name or None,
                "rarities": [r.strip() for r in rarity_text.split(",") if r.strip()],
            }
        )
    return printings


def get_images(image_field, failures, pageid, title):
    """Turn the image field into a list of {"index", "file", "art_only"} entries.

    Each line looks like: index; card image file; a bool indicating whether the image is art (square)
    or a full card.

    Each row uses the art-only file if it has one (art_only True), otherwise the full card
    image (art_only False), the same rule the wiki uses. Rows with neither file are
    reported to failures (keyed by the card's pageid and title) and left out.
    """
    if not image_field:
        return []
    if ";" not in image_field:
        return [{"index": "1", "file": image_field, "art_only": False}]

    images = []
    for line in image_field.splitlines():
        if ";" not in line:
            continue
        index, card_image, art_image = split_fields(line, 3)
        if art_image:
            images.append({"index": index, "file": art_image, "art_only": True})
        elif card_image:
            images.append({"index": index, "file": card_image, "art_only": False})
        else:
            failures.add("card_image_row_blank", page_id=pageid, title=title,
                         comment=f"image row {index!r} has neither a card image nor an art image")
    return images


def get_card_type(card_fields):
    """
    The single card type for a card: the card_type field if the template has one (Spell, Trap, ...),
    otherwise the most specific monster type found in the "types" field, otherwise "Monster".

    The types field looks like "Dragon / Synchro / Effect".
    """
    card_type = card_fields.get("card_type")
    if card_type:
        return card_type

    monster_types = {part.strip().lower() for part in card_fields.get("types", "").split("/")}
    for specific_type in SPECIFIC_MONSTER_TYPES:
        if specific_type.lower() in monster_types:
            return specific_type
    return "Monster"