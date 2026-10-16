import re
from datetime import datetime

import wikitextparser as wtp

# Game for every region code. Region codes are the keys in `<region>_release_date` and
# `<region>_prefix`; uppercased, they're also the codes in {{Set navigation | lists = ...}}.
REGION_GAME = {
    "jp": "OCG", "kr": "OCG", "sc": "OCG", "ae": "OCG", "tc": "OCG",
    "en": "TCG", "na": "TCG", "eu": "TCG", "oc": "TCG", "es": "TCG",
    "fr": "TCG", "de": "TCG", "it": "TCG", "sp": "TCG", "pt": "TCG",
}
# `<lang>_name` keys use language codes; only these differ from the region code.
LANG_REGION = {"ja": "jp", "ko": "kr", "es": "sp"}

# The one whitelist: regions whose data we keep (names, release dates). Add codes here later.
KEEP = {"en", "na", "jp"}
# Language used for each record's display name.
PRIMARY_LANG = {"TCG": "en", "OCG": "ja"}

RUBY = re.compile(r"\{\{\s*Ruby\s*\|\s*([^|}]*?)\s*\|[^}]*\}\}", re.I)
INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff]")


def parse_infobox_set(wikitext):
    """Return the Infobox set template's fields as a {name: value} dict."""
    parsed = wtp.parse(wikitext)
    for template in parsed.templates:
        if template.name.strip().lower() == "infobox set":
            return {
                arg.name.strip(): INVISIBLE.sub("", arg.value).strip()
                for arg in template.arguments
            }
    return None


def _in_game(region, game):
    return region in KEEP and REGION_GAME.get(region) == game


def clean(value):
    """Unwrap {{Ruby}}, [[links]] and comments down to plain text."""
    return wtp.parse(RUBY.sub(r"\1", value)).plain_text().strip()


def get_names(fields, game):
    """*_name fields for `game`'s kept languages, keyed by language ('ja', 'ja_trans', ...)."""
    return {
        key[: -len("_name")]: clean(value)
        for key, value in fields.items()
        if key.endswith("_name") and value
        and _in_game(LANG_REGION.get(lang := key.split("_")[0], lang), game)
    }


def to_iso(text):
    """Full dates only; partial ones ("May 2007") stay None instead of guessing."""
    try:
        return datetime.strptime(text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def get_release_dates(fields):
    """{region: {'text', 'iso'}} for ALL regions; fans out combined keys like `fr/de/it/sp_release_date`.

    Left unfiltered on purpose: it's the fallback for game detection. The whitelist
    is applied when the final records are built.
    """
    dates = {}
    for key, value in fields.items():
        if not key.endswith("_release_date"):
            continue
        text = clean(value)
        if not text:
            continue
        for region in key[: -len("_release_date")].split("/"):
            dates[region.strip()] = {"text": text, "iso": to_iso(text)}
    return dates


def games_from_lists(wikitext):
    for template in wtp.parse(wikitext).templates:
        if template.name.strip().lower() == "set navigation":
            for arg in template.arguments:
                if arg.name.strip() == "lists":
                    codes = [c.strip().lower() for c in arg.value.split(",")]
                    return {REGION_GAME[c] for c in codes if c in REGION_GAME}
    return set()


def games_from_dates(release_dates):
    return {REGION_GAME[r] for r in release_dates if r in REGION_GAME}


def _filter_by_game(dict_keyed_by_region, game):
    return {
        region: value for region, value in dict_keyed_by_region.items() if _in_game(region, game)
    }


def parse_set_page(page):
    """`page` is one of the raw dumps (pageid, title, wikitext, ...).

    Returns one record per game (OCG/TCG) the set belongs to, or [] if the page
    has no infobox or no game could be determined.
    """
    wikitext = page["wikitext"]
    fields = parse_infobox_set(wikitext)
    if fields is None:
        raise NoInfobox()

    all_dates = get_release_dates(fields)
    # Lists is primary; release-date regions only if there's no usable Lists field.
    games = games_from_lists(wikitext) or games_from_dates(all_dates)
    if not games:
        raise NoGameDetermined(f"Couldn't determine game from wikitext {wikitext} or date regions: {sorted(all_dates)}")

    records = []
    for game in sorted(games):
        names = get_names(fields, game)
        records.append({
            "page_id": page["pageid"],
            "title": page["title"],
            "game": game,
            "name": names.get(PRIMARY_LANG[game]) or page["title"],
            "names": names,
            "image": fields.get("image") or None,
            "prefix": fields.get("prefix") or None,
            "postfix": fields.get("postfix") or None,
            "release_dates": _filter_by_game(all_dates, game),
        })
    return records


class SetParseError(Exception):
    reason = "parse_error"

class NoInfobox(SetParseError):
    reason = "no_infobox"

class NoGameDetermined(SetParseError):
    reason = "no_game"