"""Finding the set record that a card printing's set name refers to.

Matching is exact: a printing's set name must equal a set record's title.
As a last resort, when no title matches, a manual alias from set_aliases.json
(keyed by region and alias name, pointing at a set_id) is tried.
"""
import json
from collections import defaultdict, namedtuple
from pathlib import Path

DEFAULT_ALIASES_PATH = Path("set_aliases.json")

# Result of a lookup. On success `set_record` is filled in and the failure fields are empty.
# On failure `set_record` is None and `failure_kind` is "ambiguous_set" or "set_not_found".
SetLookup = namedtuple("SetLookup", ["set_record", "failure_kind", "failure_details"])


def found(set_record):
    return SetLookup(set_record, None, {})


def ambiguous(candidate_set_ids):
    return SetLookup(None, "ambiguous_set", {"candidates": sorted(candidate_set_ids)})


def not_found(details=None):
    return SetLookup(None, "set_not_found", details or {})


def load_set_aliases(path=DEFAULT_ALIASES_PATH):
    """Read the manual set-name aliases. A missing file just means there are none.

    The file is a JSON list of {"region", "alias", "set_id", "note"?} entries.
    """
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class SetIndex:
    """All set records, indexed so a (set name, region) can be looked up.

    A set's id is "<page_id>-<region>".
    """

    # A card printing's region is where it was released (e.g. "na"), while a set record's
    # region comes from the set page's `lists` (e.g. "en"). English-language sets can be
    # released in NA only (Duel Terminal 3), so these are tried as a second choice.
    REGION_FALLBACKS = {"na": ["en"], "en": ["na"]}

    def __init__(self, set_records, failures):
        self.sets_by_id = {}
        self.sets_by_title = defaultdict(list)       # (region, title) -> [set records]
        self.regions_by_title = defaultdict(set)     # title -> {regions}, only to explain failures
        self.set_ids_by_alias = {}                   # (region, alias) -> set_id
        self.used_aliases = set()                    # (region, alias) keys that resolved a printing

        for record in set_records:
            self._add_set(record, failures)
        for entry in load_set_aliases():
            self._add_alias(entry, failures)

    # ------------------------------------------------------------ building the index
    def _add_set(self, record, failures):
        title = record.get("title")
        region = record.get("region")
        page_id = record.get("page_id")

        if not title or not region or page_id is None:
            failures.add("malformed_set", title=title, region=region, page_id=page_id)
            return

        set_id = f"{page_id}-{region}"
        if set_id in self.sets_by_id:
            failures.add("duplicate_set", set_id=set_id, title=title)
            return

        same_title_sets = self.sets_by_title[(region, title)]
        if same_title_sets:
            failures.add("duplicate_set_title", region=region, title=title, set_id=set_id,
                         other=[other["set_id"] for other in same_title_sets])

        set_record = {**record, "set_id": set_id}
        self.sets_by_id[set_id] = set_record
        self.sets_by_title[(region, title)].append(set_record)
        self.regions_by_title[title].add(region)

    def _add_alias(self, entry, failures):
        """Register one manual alias. Bad entries are logged and skipped."""
        if not isinstance(entry, dict):
            failures.add("malformed_set_alias", entry=entry)
            return

        region = entry.get("region")
        alias = entry.get("alias")
        target_set_id = entry.get("target_set_id")

        if not region or not alias or not target_set_id:
            failures.add("malformed_set_alias", entry=entry)
            return

        if target_set_id not in self.sets_by_id:
            failures.add("set_alias_target_missing", region=region, alias=alias, set_id=target_set_id)
            return

        key = (region, alias)
        if key in self.set_ids_by_alias:
            failures.add("duplicate_set_alias", region=region, alias=alias, set_id=target_set_id,
                         other=self.set_ids_by_alias[key])
            return

        self.set_ids_by_alias[key] = target_set_id

    # ------------------------------------------------------------ looking things up
    def find(self, set_name, region):
        """Find the set record whose title equals `set_name`.

        Tries the printing's own region first. Only if nothing matches there
        are the fallback regions tried. An ambiguous match stops the search.

        Manual aliases are a last resort: they are only consulted when no title
        matched in any region, i.e. when this would otherwise be a set_not_found.
        """
        regions_to_try = [region] + self.REGION_FALLBACKS.get(region, [])

        for region_to_try in regions_to_try:
            lookup = self._find_in_region(set_name, region_to_try)
            if lookup.set_record is not None:
                return lookup
            if lookup.failure_kind == "ambiguous_set":
                return lookup

        for region_to_try in regions_to_try:
            alias_set_id = self.set_ids_by_alias.get((region_to_try, set_name))
            if alias_set_id is not None:
                self.used_aliases.add((region_to_try, set_name))
                return found(self.sets_by_id[alias_set_id])

        # Hint for debugging: other regions that do have a set with exactly this title.
        return not_found({"regions_with_title": sorted(self.regions_by_title.get(set_name, []))})

    def _find_in_region(self, set_name, region):
        candidates = self.sets_by_title.get((region, set_name), [])

        if len(candidates) == 1:
            return found(candidates[0])
        if len(candidates) > 1:
            return ambiguous(candidate["set_id"] for candidate in candidates)
        return not_found()

    # ------------------------------------------------------------ after the run
    def report_unused_aliases(self, failures):
        """Log every manual alias that never resolved a printing.

        Call once after all cards have been resolved. Only meaningful for a full run:
        on a partial run, aliases for the skipped cards will be reported too.
        """
        unused = set(self.set_ids_by_alias) - self.used_aliases
        for region, alias in sorted(unused):
            failures.add("unused_set_alias", region=region, alias=alias,
                        set_id=self.set_ids_by_alias[(region, alias)])