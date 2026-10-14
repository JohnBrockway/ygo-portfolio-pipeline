import wikitextparser as wtp

# Used as both a mapping and a filter; sets that do not appear as keys will not
# be added to the output.
SET_FIELDS = {
    "en_sets": "en",
    "na_sets": "na",
    "jp_sets": "jp",
}

def parse_card_table_2(wikitext):
    """Return the CardTable2 template's fields as a {name: value} dict."""
    parsed = wtp.parse(wikitext)
    for template in parsed.templates:
        if template.name.strip() == "CardTable2":
            return {arg.name.strip(): arg.value.strip() for arg in template.arguments}
    return None

def get_printings(wikitext_dict):
    printings = []
    for field_name, region in SET_FIELDS.items():
        if field_name in wikitext_dict:
            printings.extend(parse_sets_for_region(wikitext_dict[field_name], region))
    return printings


def parse_sets_for_region(value, region):
    """Turn a *_sets field into a list of printings.

    Each line is formatted as: set number; set name; rarity, rarity
    However, for Series 1 cards (and some other exceptions), set number may be absent
    """
    printings = []
    for line in value.splitlines():
        if ";" not in line:
            continue
        parts = [part.strip() for part in line.split(";")]
        rarity_text = parts[2] if len(parts) > 2 else ""
        printings.append(
            {
                "region": region,
                "set_number": parts[0] or None,
                "set_name": parts[1] if len(parts) > 1 else None,
                "rarities": [r.strip() for r in rarity_text.split(",") if r.strip()],
            }
        )
    return printings


def get_images(image_field):
    """Turn the image field into a list of rows.

    Each line looks like: index; card image file; art-only file (optional)
    A page with a single image may instead just be one filename with no semicolons.
    """
    if ";" not in image_field:
        return [{"index": "1", "card_image": image_field, "art_image": None}]
    rows = []
    for line in image_field.splitlines():
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 2:
            continue
        rows.append(
            {
                "index": parts[0],
                "card_image": parts[1] or None,
                "art_image": (parts[2] if len(parts) > 2 else "") or None,
            }
        )
    return rows