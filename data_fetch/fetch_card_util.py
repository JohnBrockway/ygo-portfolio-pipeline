"""The card categories to fetch, one per wiki category of cards."""

# One entry per wiki category of cards. Every card found in a category is tagged with that
# category's "game" (a fixed set of values the master build and the app can rely on), and
# its records are saved in <raw-out-dir>/<folder>.
CARD_CATEGORIES = [
    {"category": "Category:Duel Monsters cards", "game": "duel_monsters", "folder": "duel_monsters_cards"},
    {"category": "Category:Rush Duel cards", "game": "rush_duel", "folder": "rush_duel_cards"},
    {"category": "Category:Monster Tokens", "game": "duel_monsters", "folder": "monster_token_cards"},
]