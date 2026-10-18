from regions import WHITELISTED_REGIONS

import wikitextparser as wtp


def parse_card_table_2(wikitext):
    """Return the CardTable2 template's fields as a {name: value} dict, or None if the page doesn't have that template."""
    parsed = wtp.parse(wikitext)
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


def get_images(image_field):
    """Turn the image field into a list of rows.

    Each line looks like: index; card image file; art-only file (optional)
    A page with a single image may instead just be one filename with no semicolons.
    """
    if not image_field:
        return []
    if ";" not in image_field:
        return [{"index": "1", "card_image": image_field, "art_image": None}]

    rows = []
    for line in image_field.splitlines():
        if ";" not in line:
            continue
        index, card_image, art_image = split_fields(line, 3)
        rows.append(
            {
                "index": index,
                "card_image": card_image or None,
                "art_image": art_image or None,
            }
        )
    return rows
