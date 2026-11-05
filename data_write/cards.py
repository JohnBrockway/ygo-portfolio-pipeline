"""Turning a raw card record into a master card record."""

# Yugipedia writes 'none' for 'no value', so these all count as blank.
BLANK_VALUES = {"", "none", "null", "n/a"}


def clean_id(value):
    """Return the id as a stripped string, or None if it is missing or a blank placeholder."""
    if value is None:
        return None
    text = str(value).strip()
    if text.casefold() in BLANK_VALUES:
        return None
    return text


def choose_card_id(card):
    """Pick the card's id: konami_id, else password, else wiki pageid.

    A letter prefix (k / p / w) keeps the three id spaces from colliding.
    Returns None if the card has none of them.
    """
    konami_id = clean_id(card.get("konami_id"))
    if konami_id:
        return f"k{konami_id}"

    password = clean_id(card.get("password"))
    if password:
        return f"p{password}"

    if card.get("pageid") is not None:
        return f"w{card['pageid']}"

    return None


def build_card_images(card_id, card, image_index, failures):
    """The card's images, each with `thumb` (the thumbnail's file name) if one was downloaded.

    Images with no thumbnail are kept, without the field, and reported.
    """
    images = []
    for image in card.get("images", []):
        thumb = image_index.get(image["file"])
        if thumb is None:
            failures.add("card_image_missing_thumbnail", card_id=card_id, title=card.get("title"),
                         index=image["index"], file=image["file"])
            images.append(image)
        else:
            images.append({**image, "thumb": thumb})
    return images


def build_card_record(card_id, card, image_index, failures):
    return {
        "card_id": card_id,
        "pageid": card.get("pageid"),
        "title": card.get("title"),
        "game": card["game"],
        "name_ja": card.get("name_ja"),
        "konami_id": clean_id(card.get("konami_id")),
        "password": clean_id(card.get("password")),
        "card_type": card.get("card_type"),
        "images": build_card_images(card_id, card, image_index, failures),
    }