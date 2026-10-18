"""Which regions the app tracks. The one place to edit when adding a region."""

# Regions we save set records and card printings for. Add codes here (e.g. "it" or "sc")
# to include them; anything else is ignored and doesn't exist for purposes of the app.
# These are REGION codes: the ones in `<region>_release_date`, `<region>_sets` and,
# uppercased, {{Set navigation | lists = ...}}. They are not language codes:
# "jp" is Japan, while "ja" is Japanese-Asian, a different region.
WHITELISTED_REGIONS = {"en", "na", "jp"}