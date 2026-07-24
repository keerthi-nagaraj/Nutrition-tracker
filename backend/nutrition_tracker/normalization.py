"""Canonicalizes a Gemini-detected food name before FDC search (regional-name mapping, abbreviation expansion, filler-word stripping)."""

import csv
import re

from .config import REGIONAL_MAP_CSV_PATH

# Adjectives that don't affect nutrition — stripped so they don't dilute the
# FDC text match (e.g. "delicious homemade fried rice" -> "fried rice").
_FILLER_WORDS = {
    "delicious", "homemade", "fresh", "tasty", "yummy", "nice", "lovely",
    "amazing", "wonderful", "great", "perfect", "beautiful",
}

# Common abbreviations expanded before search.
_ABBREVIATIONS = {
    "pb": "peanut butter",
    "veg": "vegetable",
    "nonveg": "non-vegetarian",
}

_WORD_RE = re.compile(r"[A-Za-z]+")


def _load_regional_map() -> dict[str, str]:
    """alias -> canonical, lowercased; missing/unreadable file degrades to an empty map rather than crashing startup."""
    try:
        with open(REGIONAL_MAP_CSV_PATH, "r", encoding="utf-8") as f:
            return {row["alias"].strip().lower(): row["canonical"].strip() for row in csv.DictReader(f)}
    except OSError:
        return {}


_REGIONAL_MAP = _load_regional_map()


def normalize_food_name(name: str) -> str:
    """Maps regional names, expands abbreviations, strips filler words; never returns an empty string."""
    if not name:
        return name

    stripped = name.strip()

    # Exact whole-name regional match only (e.g. "dal" -> "cooked yellow
    # lentils") — a compound dish like "dal makhani" is its own thing and
    # isn't rewritten just because it contains a mapped word.
    canonical = _REGIONAL_MAP.get(stripped.lower())
    if canonical:
        return canonical

    def replace_word(match: re.Match) -> str:
        word = match.group(0)
        lower = word.lower()
        if lower in _ABBREVIATIONS:
            return _ABBREVIATIONS[lower]
        if lower in _FILLER_WORDS:
            return ""
        return word

    normalized = _WORD_RE.sub(replace_word, stripped)
    normalized = re.sub(r"\s+", " ", normalized).strip(" ,")
    return normalized or stripped
