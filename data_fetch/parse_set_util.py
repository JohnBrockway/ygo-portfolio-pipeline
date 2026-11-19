"""Parsing of set page wikitext: the Infobox set and Set navigation templates, into one record per region."""
import re
from datetime import datetime

import wikitextparser as wtp

from data_fetch.regions import WHITELISTED_REGIONS
from data_fetch.wikitext_util import find_template

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
# Regions whose data isn't (always) filed under their own code. Often when a region has
# subregions, ex. English sets will have the card list identified by EN, but release dates and
# editions can be broken down into NA, EU, etc. Fallbacks are tried in order, after and only if
# the top-level region produces nothing.
SOURCE_REGION_FALLBACK = {"en": ["na", "eu"]}

# Edition slugs, each paired with the {{Set navigation}} field that lists the regions that have it.
# Order is canonical, highest edition first: editions[0] is a set's "best" edition.
EDITION_FIELDS = [
    ("1st_edition", "1e_galleries"),
    ("limited", "le_galleries"),
    ("unlimited", "ue_galleries"),
]

INVISIBLE = re.compile("[\u200b-\u200d\u2060\ufeff]")


def parse_infobox_set(parsed):
    """Returns the Infobox set template's fields as a {name: value} dict, or None if the page has none.

    `parsed` is the page's wikitext as parsed by wikitextparser.
    """
    template = find_template(parsed, "infobox set")
    if template is None:
        return None
    return {
        arg.name.strip(): INVISIBLE.sub("", arg.value).strip()
        for arg in template.arguments
    }


def clean(value):
    """Strip wiki markup down to readable text, but keep templates like {{Ruby|墓|はか}} as written.

    plain_text() turns [[links]] into their display text and removes '''bold'''/''italic''
    markers and <!-- comments -->. It would also remove templates by default, which would
    lose the Ruby readings, so replace_templates=False tells it to leave them alone.
    """
    return wtp.parse(value).plain_text(replace_templates=False).strip()


def primary_lang(region):
    """Primary language for the region; used to pick the display name of the set ('jp' -> 'ja', 'na' -> 'en')."""
    region_key = NAME_ALIAS.get(region, region)
    return REGION_TO_LANG_MAP.get(region_key, region_key)


def get_all_names(fields, region):
    """
    All *_name fields present in fields that are used for region, keyed by
    the part before `_name` ('ja', 'romaji', 'ja_trans', ...).
    """
    region_key = NAME_ALIAS.get(region, region)
    names = {}
    for key, value in fields.items():
        if not key.endswith("_name"):
            continue
        lang = key.split("_")[0]
        if LANG_TO_REGION_MAP.get(lang, lang) != region_key:
            continue
        text = clean(value)
        if text:
            names[key.removesuffix("_name")] = text
    return names


def to_iso(text):
    """Full dates only; partial ones ("May 2007") stay None instead of guessing."""
    try:
        return datetime.strptime(text, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def get_region_values(fields, suffix):
    """{region: text} for every `<region>_<suffix>` key; fans out combined keys like `fr/de/it/sp_release_date`."""
    values = {}
    for key, value in fields.items():
        if not key.endswith(f"_{suffix}"):
            continue
        text = clean(value)
        if not text:
            continue
        for region in key.removesuffix(f"_{suffix}").split("/"):
            values[region.strip()] = text
    return values


def get_release_dates(fields):
    """{region: {'text', 'iso'}} for ALL regions (unfiltered: its regions are the Lists fallback)."""
    return {
        region: {"text": text, "iso": to_iso(text)}
        for region, text in get_region_values(fields, "release_date").items()
    }


def pick_release_date(all_dates, region):
    """The region's own date, else the first SOURCE_REGION_FALLBACK region that has one; None if neither."""
    for source in [region, *SOURCE_REGION_FALLBACK.get(region, [])]:
        if source in all_dates:
            return {**all_dates[source], "source_region": source}
    return None


def get_set_navigation(parsed):
    """{arg name: set of lowercased region codes} from {{Set navigation}}; {} if the template is absent.

    `parsed` is the page's wikitext as parsed by wikitextparser.

    Holds Lists (which regions the set was released in) and the edition fields
    (1e_galleries, ue_galleries, le_galleries), all written as comma-separated codes.
    """
    template = find_template(parsed, "set navigation")
    if template is None:
        return {}
    return {
        arg.name.strip(): {c.strip().lower() for c in arg.value.split(",") if c.strip()}
        for arg in template.arguments
    }


def pick_editions(navigation, region, kept):
    """Edition slugs for the region, in priority order; None if the page lists no edition for it.

    Tries the region's own code first, then its SOURCE_REGION_FALLBACK regions in order. A fallback
    region that has a record of its own (is in kept) is skipped: its editions belong to that
    record, and borrowing them would hide a gap in the data instead of flagging it. (Dates have
    no such guard; they borrow regardless.)
    """
    for source in [region, *SOURCE_REGION_FALLBACK.get(region, [])]:
        if source != region and source in kept:
            continue
        editions = [
            slug for slug, field in EDITION_FIELDS
            if source in navigation.get(field, set())
        ]
        if editions:
            return editions
    return None


def parse_set_page(page, failures):
    """`page` is one raw page from the wiki (pageid, title, revisions, ...).

    Returns one record per whitelisted region the set was released in. If the page can't
    produce a single record, the reason goes to `failures` and the result is [].
    """
    revisions = page.get("revisions")
    if not revisions:
        failures.add("absent_or_malformed_wikitext", page_id=page["pageid"], title=page["title"])
        return []
    wikitext = revisions[0]["slots"]["main"]["content"]
    parsed = wtp.parse(wikitext)
    fields = parse_infobox_set(parsed)
    if fields is None:
        failures.add("no_infobox", page_id=page["pageid"], title=page["title"])
        return []
    video_games = clean(fields.get("appears_in_video_games", ""))
    if video_games:
        failures.add("video_game_set", page_id=page["pageid"], title=page["title"],
                     comment=f"Video game set: {video_games}")
        return []

    all_dates = get_release_dates(fields)
    prefixes = get_region_values(fields, "prefix")
    postfixes = get_region_values(fields, "postfix")
    navigation = get_set_navigation(parsed)

    # Lists is primary; release-date used to determine regions only if there's no usable Lists field.
    regions = navigation.get("lists") or set(all_dates)
    if not regions:
        failures.add("no_region", page_id=page["pageid"], title=page["title"],
                     comment="No Lists field or release dates in wikitext")
        return []
    kept_regions = regions & WHITELISTED_REGIONS
    if not kept_regions:
        failures.add("unsupported_region", page_id=page["pageid"], title=page["title"],
                     comment=f"No whitelisted region among {sorted(regions)}")
        return []

    records = []
    for region in sorted(kept_regions):
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
            "editions": pick_editions(navigation, region, kept_regions),
        })
    return records