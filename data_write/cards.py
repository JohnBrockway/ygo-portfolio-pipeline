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


def pick_card_images(card):
    """One entry per image row: the art-only file if there is one, else the full card image.
    (Same logic the wiki uses.)"""
    images = []
    for image in card.get("images") or []:
        art_file = image.get("art_image")
        full_file = image.get("card_image")
        if not art_file and not full_file:
            continue
        images.append({
            "index": image.get("index"),
            "file": art_file or full_file,
            "art_only": bool(art_file),
        })
    return images


def build_card_record(card_id, card):
    return {
        "card_id": card_id,
        "pageid": card.get("pageid"),
        "title": card.get("title"),
        "name_ja": card.get("name_ja"),
        "konami_id": clean_id(card.get("konami_id")),
        "password": clean_id(card.get("password")),
        "card_type": card.get("card_type"),
        "images": pick_card_images(card),
    }