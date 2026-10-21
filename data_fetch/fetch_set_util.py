"""
Fetch loop for set pages.

Cards live in one flat category, but Yugipedia files Sets in NESTED categories
(e.g. Category:TCG sets -> Category:TCG Booster Packs -> Rarity Collection 5),
and the API only returns a category's direct members. So this is two phases:

  1. discover_categories(): breadth-first walk over subcategories only (titles, no
     wikitext). The `tree` dict is both the result and the visited set. A category is 
     added the moment it is first seen, so cycles and shared subcategories can never
     be queued twice.
  2. fetch_tree_pages(): download each discovered category's direct page members with
     wikitext, de-duplicated by pageid (a page can sit in several categories).
"""
import re
from collections import deque

from mediawiki_util import query, query_pages


def normalize_category(title):
    """'TCG_sets' / 'category:TCG_sets' -> 'Category:TCG sets' (the form the API returns)."""
    t = re.sub(r"[ _]+", " ", title).strip()
    if t.lower().startswith("category:"):
        t = t[len("category:"):].strip()
    return "Category:" + t[:1].upper() + t[1:]


def discover_categories(session, roots, exclude=(), max_categories=2000):
    """Return {category: [direct child categories]} for everything under `roots`.

    `exclude` skips those categories (and so their subtrees). `max_categories` is a
    runaway guard in case a root is wrong and the walk balloons.
    """
    excluded = {normalize_category(c) for c in exclude}
    tree = {}
    queue = deque()

    for root in map(normalize_category, roots):
        if root not in tree and root not in excluded:
            tree[root] = []
            queue.append(root)

    while queue:
        category = queue.popleft()
        params = {
            "list": "categorymembers",
            "cmtitle": category,
            "cmtype": "subcat",     # subcategories only
            "cmprop": "title",
            "cmlimit": "max",
        }
        for data in query(session, params):
            for member in data.get("query", {}).get("categorymembers", []):
                child = normalize_category(member["title"])
                if child in excluded:
                    continue
                if child not in tree[category]:
                    tree[category].append(child)
                if child in tree:
                    # Reached again: a cycle, or a subcategory shared by two parents.
                    continue
                if len(tree) >= max_categories:
                    raise RuntimeError(
                        f"more than {max_categories} categories discovered; wrong root or runaway tree?"
                    )
                tree[child] = []
                queue.append(child)
        print(f"explored {category} ({len(tree)} known, {len(queue)} queued)")
    return tree


def fetch_tree_pages(session, categories, max_requests=None):
    """Yield direct page members of each category, once per pageid.

    `max_requests` caps the API requests spent on EACH category (dev convenience).
    """
    seen_ids = set()
    for category in categories:
        print(f"category: {category}")
        params = {
            "redirects": "true",
            "generator": "categorymembers",
            "gcmtitle": category,
            "gcmtype": "page",              # pages only; subcategories have already been handled by discover_categories
            "gcmlimit": "50",
            "prop": "revisions|info",       # same properties as the card fetch
            "rvprop": "content",
            "inprop": "url",
        }
        for page in query_pages(session, params, max_requests):
            if "revisions" not in page:
                continue                    # missing page or a batch without content
            if page["pageid"] in seen_ids:
                continue
            seen_ids.add(page["pageid"])
            yield page
