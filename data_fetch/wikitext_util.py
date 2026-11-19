"""Helpers shared by the card and set wikitext parsers."""


def find_template(parsed, template_name):
    """The first template in `parsed` (a wikitextparser result) named `template_name`, or None.

    Template names are compared ignoring case and surrounding whitespace, so `template_name`
    is given in lowercase.
    """
    for template in parsed.templates:
        if template.name.strip().lower() == template_name:
            return template
    return None
 