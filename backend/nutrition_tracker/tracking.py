"""Tool 4 model logic: scales merged per-100g nutrition by weight and sums the full 8-nutrient totals."""

import re

from .config import NUTRIENTS
from .providers import lookup_nutrition_batch

_POSITION_SUFFIX_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _strip_position_descriptor(name: str) -> str:
    """Strips a trailing positional parenthetical like ' (top)' that would confuse the nutrition-provider text search."""
    return _POSITION_SUFFIX_RE.sub("", name).strip()


def _resolve_weight(f: dict) -> float:
    """Accepts weight_g, estimated_weight_g, or consumed_weight_g — whichever key the upstream tool used."""
    return float(f.get("weight_g", f.get("estimated_weight_g", f.get("consumed_weight_g", 0))))


def _normalize_and_dedupe(foods: list[dict]) -> list[dict]:
    """Dedupes to [{"name", "weight_g"}, ...], merging same-name foods (case/whitespace-insensitive) so none are double-counted."""
    merged: dict[str, dict] = {}
    for f in foods:
        name = _strip_position_descriptor(f["name"])
        key = name.lower()
        weight_g = _resolve_weight(f)
        if key in merged:
            merged[key]["weight_g"] += weight_g
        else:
            merged[key] = {"name": name, "weight_g": weight_g}
    return list(merged.values())


def _scale(per_100g: dict | None, grams: float) -> dict | None:
    """per_100g_value * (grams / 100) for every nutrient."""
    if per_100g is None:
        return None
    factor = grams / 100.0
    return {k: round(v * factor, 2) for k, v in per_100g.items()}


def _sum_totals(scaled_nutrition: list[dict | None]) -> dict:
    """Sums each nutrient across matched foods; unmatched foods are skipped entirely, never counted as zero."""
    totals = {v: 0.0 for v in NUTRIENTS.values()}
    for nutrition in scaled_nutrition:
        if nutrition is None:
            continue
        for k, v in nutrition.items():
            totals[k] += v
    return {k: round(v, 2) for k, v in totals.items()}


def estimate_meal_nutrition_impl(foods: list[dict]) -> dict:
    """Tool 4 model logic: normalizes/dedupes foods, batch-looks-up nutrition, scales by weight, and sums totals."""
    normalized = _normalize_and_dedupe(foods)

    # One shared batch call instead of looping lookup_nutrition_impl per food
    # — every food's provider calls run concurrently rather than one food's
    # providers finishing before the next food's even start.
    nutrition_infos = lookup_nutrition_batch([f["name"] for f in normalized])

    result_foods = []
    scaled_nutrition = []
    for f, nutrition_info in zip(normalized, nutrition_infos):
        scaled = _scale(nutrition_info["per_100g"], f["weight_g"])
        result_foods.append({
            "name": f["name"],
            "calories": scaled["calories"] if scaled else 0.0,
            "fdc_id": nutrition_info["fdc_id"],
            "match_confidence": nutrition_info["match_confidence"],
            "matched_description": nutrition_info["matched_description"],
            "source": nutrition_info["source"],
            "source_id": nutrition_info["source_id"],
            "sources": nutrition_info["sources"],
        })
        scaled_nutrition.append(scaled)
        if not nutrition_info["found"]:
            print(f"[estimate_meal_nutrition] UNMATCHED: '{f['name']}' excluded from totals")

    return {
        "foods": result_foods,
        "nutrition": _sum_totals(scaled_nutrition),
    }
