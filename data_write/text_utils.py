"""Small string helpers used when building ids and set numbers."""
import re


def slugify(text):
    """'Ultra Rare' -> 'ultra-rare'"""
    text = re.sub(r"[^A-Za-z0-9]+", "-", str(text))
    return text.strip("-").lower()


def compact_uppercase(text):
    """'Duel Terminal 3' -> 'DUELTERMINAL3'"""
    text = re.sub(r"[^A-Za-z0-9]+", "", str(text))
    return text.upper()