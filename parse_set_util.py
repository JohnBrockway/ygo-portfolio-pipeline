import re
from datetime import datetime

import wikitextparser as wtp

# Regions we save records for. Add codes here to include in master set, otherwise they
# are ignored and don't exist for purposes of the app.
# Codes are the keys in  <region>_release_date / <region>_prefix and, uppercased,
# the codes in {{Set navigation | lists = ...}}. e.g. "it", "sc"
WHITELISTED_REGIONS = {"en", "na", "jp"}

# There are two different namespaces of codes present in dict keys
#   - Regions ("jp", "en", etc.)
#       Used in fields like xx_release_date, xx_prefix, and maybe most importantly
#       in the Set Navigation -> Lists field, used as the source of truth for fanning
#       out 1 set page into multiple unique sets by language.
#   - Name keys
#       Many languages have a language code matching the region, but not universally.
#       For example, the "jp" region identifies card name via "ja_name".
# Notably, these namespaces can have collisions; "ja" is also a region in itself (Japanese-Asian).
# Ensure to use region whenever possible, and use these maps (with region as the default)
# when specifically needing conversion.
LANG_TO_REGION_MAP = {"ja": "jp", "romaji": "jp", "ko": "kr", "es": "sp"}
# Display-name language per region, when it isn't the region code.
REGION_TO_LANG_MAP = {"jp": "ja", "kr": "ko", "sp": "es"}
# Regions with no `<region>_name` of their own; they reuse another region's names.
NAME_ALIAS = {"na": "en"}
# Regions where the release dates aren't (always) directly referred to as <region>_release_date
# in the infobox. Often when a region has subregions, ex. English sets will have the card list
# identified by EN, but release dates can be broken down into NA, EU, etc. Fallbacks are tried
# in order, after and only if the top-level region produces no date
DATE_FALLBACK = {"en": ["na", "eu", "oc"]}

RUBY = re.compile(r"\{\{\s*Ruby\s*\|\s*([^|}]*?)\s*\|[^}]*\}\}", re.I)
INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff]")


def parse_infobox_set(wikitext):
    """Returns the Infobox set template's fields as a {name: value} dict."""
    parsed = wtp.parse(wikitext)
    for template in parsed.templates:
        if template.name.strip().lower() == "infobox set":
            return {
                arg.name.strip(): INVISIBLE.sub("", arg.value).strip()
                for arg in template.arguments
            }
    return None


def clean(value):
    """Unwrap {{Ruby}}, [[links]] and comments down to plain text."""
    return wtp.parse(RUBY.sub(r"\1", value)).plain_text().strip()


def primary_lang(region):
    """Primary language for the region; used to pick the display name of the set ('jp' -> 'ja', 'na' -> 'en')."""
    region_key = NAME_ALIAS.get(region, region)
    return REGION_TO_LANG_MAP.get(region_key, region_key)


def get_all_names(fields, region):
    """All *_name fields for region, keyed byl anguage ('ja', 'romaji', 'ja_trans', ...)."""
    region_key = NAME_ALIAS.get(region, region)
    return {
        key[: -len("_name")]: clean(value)
        for key, value in fields.items()
        if key.endswith("_name") and value
        and LANG_TO_REGION_MAP.get(lang := key.split("_")[0], lang) == region_key
    }


def to_iso(text):
    """Full dates only; partial ones ("May 2007") stay None instead of guessing."""
    try:
        return datetime.strptime(text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def pick_release_date(all_dates, region):
    """The region's own date, else the first DATE_FALLBACK region that has one; None if neither."""
    for source in [region, *DATE_FALLBACK.get(region, [])]:
        if source in all_dates:
            return {**all_dates[source], "source_region": source}
    return None


def get_release_dates(fields):
    """{region: {'text', 'iso'}} for ALL regions (unfiltered: its regions are the Lists fallback)."""
    return {
        region: {"text": text, "iso": to_iso(text)}
        for region, text in get_region_values(fields, "release_date").items()
    }


def get_region_values(fields, suffix):
    """{region: text} for every `<region>_<suffix>` key; fans out combined keys like `fr/de/it/sp_release_date`."""
    values = {}
    for key, value in fields.items():
        if not key.endswith(f"_{suffix}"):
            continue
        text = clean(value)
        if not text:
            continue
        for region in key[: -len(suffix) - 1].split("/"):
            values[region.strip()] = text
    return values


def get_listed_regions(wikitext):
    """Lowercased region codes from {{Set navigation | lists = EN, NA, JP}}; empty set if absent."""
    for template in wtp.parse(wikitext).templates:
        if template.name.strip().lower() == "set navigation":
            for arg in template.arguments:
                if arg.name.strip() == "lists":
                    return {c.strip().lower() for c in arg.value.split(",") if c.strip()}
    return set()


def parse_set_page(page):
    """`page` is one of the raw dumps (pageid, title, wikitext, ...).

    Returns one record per whitelisted region the set was released in. Raises a
    SetParseError if the page can't produce a single record for any reason.
    """
    wikitext = page["wikitext"]
    fields = parse_infobox_set(wikitext)
    if fields is None:
        raise NoInfobox()

    all_dates = get_release_dates(fields)
    prefixes = get_region_values(fields, "prefix")
    postfixes = get_region_values(fields, "postfix")

    # Lists is primary; release-date used to determine regions only if there's no usable Lists field.
    regions = get_listed_regions(wikitext) or set(all_dates)
    if not regions:
        raise NoRegionDetermined(f"No Lists field or release dates in wikitext {wikitext}")
    kept = regions & WHITELISTED_REGIONS
    if not kept:
        raise UnsupportedRegion(f"No whitelisted region among {sorted(regions)}")

    records = []
    for region in sorted(kept):
        names = get_all_names(fields, region)
        records.append({
            "page_id": page["pageid"],
            "title": page["title"],
            "region": region,
            "name": names.get(primary_lang(region)) or page["title"],
            "names": names,
            "image": fields.get("image") or None,
            "prefix": prefixes.get(region) or fields.get("prefix") or None,
            "postfix": postfixes.get(region) or fields.get("postfix") or None,
            "release_date": pick_release_date(all_dates, region),
        })
    return records


class SetParseError(Exception):
    reason = "parse_error"

class NoInfobox(SetParseError):
    reason = "no_infobox"

class NoRegionDetermined(SetParseError):
    reason = "no_region"

class UnsupportedRegion(SetParseError):
    reason = "no_kept_region"