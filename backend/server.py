"""
Nutrition Tracker MCP Server
============================

Pipeline:
  photo -> Gemini Vision (food items + estimated grams + confidence)
        -> USDA FoodData Central lookup (per-100g nutrients)
        -> scale per-100g values by estimated grams
        -> sum totals across items
        -> build terminal table + markdown table + human-readable summary

Setup:
  pip install -r requirements.txt
  export GEMINI_API_KEY=...
  export USDA_API_KEY=...

Run:
  python server.py
"""

import os
import re
import json
import base64
import mimetypes
import difflib
from datetime import date, datetime

import requests
from dotenv import load_dotenv
import google.generativeai as genai
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

USDA_API_KEY = os.getenv("USDA_API_KEY")
# USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_DETAIL_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"

# USDA nutrient name -> short key used throughout this file
NUTRIENTS = {
    "Energy": "calories",
    "Protein": "protein_g",
    "Carbohydrate, by difference": "carbs_g",
    "Total lipid (fat)": "fat_g",
    "Fiber, total dietary": "fiber_g",
    "Sugars, total including NLEA": "sugar_g",
    "Sodium, Na": "sodium_mg",
}

# How much each confidence level should widen the calorie estimate range.
# Low-confidence items (oils, sauces, cheese) swing the total far more
# than high-confidence items (a whole grilled chicken breast, etc).
CONFIDENCE_VARIANCE = {"low": 0.35, "medium": 0.20, "high": 0.05}

# How many USDA search candidates to consider before picking the best
# text match, instead of blindly trusting whatever ranks #1.
USDA_CANDIDATE_COUNT = 8

# Sodium is one of the least reliable values to estimate visually
# (dressings, added salt, oil), so it's always reported as a range.
SODIUM_RANGE_FACTORS = (0.85, 1.30)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-2.5-flash")
mcp = FastMCP("nutrition-tracker")

VLM_PROMPT = """You are a nutrition estimation assistant. Look at this photo of a meal.
For each distinct food item visible:
1. Identify the food name
2. Estimate its portion size in grams, using the plate diameter
   (assume standard 10-inch/25cm plate unless stated otherwise) as your visual reference
3. Rate your confidence as high/medium/low

Respond ONLY in this JSON format, no other text:
[
  {"item": "grilled chicken breast", "grams": 120, "confidence": "high"},
  {"item": "steamed rice", "grams": 150, "confidence": "medium"}
]
"""


# ---------------------------------------------------------------------------
# Step 1 — Image loading + Vision model
# ---------------------------------------------------------------------------

def _load_image(image_path: str | None, image_base64: str | None) -> tuple[bytes, str]:
    """Load image bytes + mime type from either a file path or base64 string."""
    if image_base64:
        if image_base64.startswith("data:"):
            header, _, image_base64 = image_base64.partition(",")
            media_type = (re.match(r"data:(image/\w+);base64", header) or [None, "image/jpeg"])[1]
        else:
            media_type = "image/jpeg"
        return base64.b64decode(image_base64), media_type

    if image_path:
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
        media_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
        with open(image_path, "rb") as f:
            return f.read(), media_type

    raise ValueError("Provide either image_path or image_base64.")


def analyze_meal_image_impl(image_path: str = None, image_base64: str = None) -> list[dict]:
    """Photo -> Gemini -> [{item, grams, confidence}, ...]."""
    image_bytes, media_type = _load_image(image_path, image_base64)

    reply = gemini_model.generate_content(
        [{"mime_type": media_type, "data": image_bytes}, VLM_PROMPT]
    ).text

    match = re.search(r"\[.*\]", reply, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in model output: {reply[:200]}")
    items = json.loads(match.group(0))

    return [
        {
            "item": it.get("item", "unknown"),
            "grams": float(it.get("grams", 0)),
            "confidence": it.get("confidence", "low"),
        }
        for it in items
    ]


# ---------------------------------------------------------------------------
# Step 2 — USDA lookup
# ---------------------------------------------------------------------------

def _best_match(food_name: str, candidates: list[dict]) -> dict:
    """Pick the candidate whose description is textually closest to
    `food_name`, instead of blindly trusting USDA's #1 ranked result.

    Uses difflib's SequenceMatcher (stdlib, no extra dependency) to score
    similarity between the query and each candidate's description, and
    returns the highest-scoring candidate.
    """
    def score(candidate: dict) -> float:
        description = (candidate.get("description") or "").lower()
        return difflib.SequenceMatcher(None, food_name.lower(), description).ratio()

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0]
    print(
        f"[USDA] '{food_name}' best match (of {len(candidates)} candidates) "
        f"-> FDC ID: {best['fdcId']} | {best.get('description')} "
        f"(score={score(best):.2f})"
    )
    return best


def lookup_nutrition_impl(food_name: str) -> dict:
    """Food name -> USDA search + detail -> per-100g nutrients.

    Fetches several USDA search candidates (USDA_CANDIDATE_COUNT) and picks
    the one whose description best matches `food_name` via fuzzy text
    similarity, rather than blindly trusting whichever result USDA's search
    ranked first.
    """
    if not USDA_API_KEY:
        raise RuntimeError("USDA_API_KEY not set")

    search = requests.get(
        USDA_SEARCH_URL,
        params={
            "api_key": USDA_API_KEY,
            "query": food_name,
            "pageSize": USDA_CANDIDATE_COUNT,
            "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
        },
        timeout=15,
    )
    search.raise_for_status()
    foods = search.json().get("foods", [])

    if not foods:
        print(f"[USDA] WARNING: no match found for '{food_name}' — nutrition unavailable")
        return {
            "item": food_name, "fdc_id": None, "matched_description": None,
            "per_100g": None, "found": False,
        }

    match = _best_match(food_name, foods)
    fdc_id, description = match["fdcId"], match.get("description")

    detail = requests.get(
        USDA_DETAIL_URL.format(fdc_id=fdc_id),
        params={"api_key": USDA_API_KEY},
        timeout=15,
    ).json()

    per_100g = {v: 0.0 for v in NUTRIENTS.values()}
    for n in detail.get("foodNutrients", []):
        name = n.get("nutrient", {}).get("name") or n.get("nutrientName")
        if name in NUTRIENTS:
            per_100g[NUTRIENTS[name]] = float(n.get("amount", n.get("value", 0)) or 0)

    return {
        "item": food_name, "fdc_id": fdc_id, "matched_description": description,
        "per_100g": per_100g, "found": True,
    }


# ---------------------------------------------------------------------------
# Step 3 — Scale per-100g values by estimated grams, then sum across items
# ---------------------------------------------------------------------------

def _scale(per_100g: dict | None, grams: float) -> dict | None:
    """per_100g_value * (grams / 100) for every nutrient."""
    if per_100g is None:
        return None
    factor = grams / 100.0
    return {k: round(v * factor, 2) for k, v in per_100g.items()}


def _sum_totals(report_items: list[dict]) -> dict:
    """Sum each nutrient across matched items. Unmatched items are skipped
    entirely (never counted as zero) so totals aren't silently understated
    without a trace — see `unmatched_items` in the tool's return value."""
    totals = {v: 0.0 for v in NUTRIENTS.values()}
    for it in report_items:
        if it["nutrition"] is None:
            continue
        for k, v in it["nutrition"].items():
            totals[k] += v
    return {k: round(v, 2) for k, v in totals.items()}


# ---------------------------------------------------------------------------
# Step 4 — Uncertainty modeling
# ---------------------------------------------------------------------------

def _calorie_range(report_items: list[dict], total_calories: float) -> tuple[int, int]:
    """Widen the calorie estimate based on each item's stated confidence."""
    variance = sum(
        it["nutrition"]["calories"] * CONFIDENCE_VARIANCE.get(it["confidence"], 0.20)
        for it in report_items
        if it["nutrition"] is not None
    )
    low = max(total_calories - variance, 0)
    high = total_calories + variance
    return round(low, -1), round(high, -1)


def _sodium_range(total_sodium_mg: float) -> tuple[int, int]:
    lo_factor, hi_factor = SODIUM_RANGE_FACTORS
    return round(total_sodium_mg * lo_factor, -1), round(total_sodium_mg * hi_factor, -1)


def _uncertain_items(report_items: list[dict]) -> list[str]:
    """Items flagged low/medium confidence — the ones driving the range."""
    return [it["item"] for it in report_items if it["confidence"] in ("low", "medium")]


def _unmatched_items(report_items: list[dict]) -> list[str]:
    return [it["item"] for it in report_items if it["nutrition"] is None]


# ---------------------------------------------------------------------------
# Step 5 — Output builders (terminal table, markdown table, text summary)
# ---------------------------------------------------------------------------

def _print_item_table(report_items: list[dict]) -> None:
    """Per-item terminal table: Item, FDC ID, Confidence, Calories."""
    print(f"\n{'Item':<25}{'FDC ID':<10}{'Confidence':<12}{'Calories':<10}")
    print("-" * 57)
    for it in report_items:
        fdc = it["fdc_id"] if it["fdc_id"] is not None else "N/A"
        cal = it["nutrition"]["calories"] if it["nutrition"] else "N/A"
        print(f"{it['item']:<25}{str(fdc):<10}{it['confidence']:<12}{str(cal):<10}")
    print()


def _build_table(report_items: list[dict]) -> str:
    """Full terminal + markdown table: Item, FDC ID, Portion, macros."""
    cols = ["Item", "FDC ID", "Portion", "Calories", "Protein", "Carbs", "Fat"]
    widths = [25, 10, 12, 10, 10, 10, 10]

    def fmt_row(vals):
        return "".join(f"{str(v):<{w}}" for v, w in zip(vals, widths))

    lines = [fmt_row(cols), "-" * sum(widths)]
    md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]

    for it in report_items:
        n = it["nutrition"]
        fdc = it["fdc_id"] if it["fdc_id"] is not None else "N/A"
        portion = f"{it['estimated_grams']}g"
        vals = [it["item"], fdc, portion] + (
            ["N/A"] * 4 if n is None else [n["calories"], n["protein_g"], n["carbs_g"], n["fat_g"]]
        )
        lines.append(fmt_row(vals))
        md.append("| " + " | ".join(str(v) for v in vals) + " |")

    print("\n" + "\n".join(lines) + "\n")
    return "\n".join(md)


def _build_meal_summary(report_items: list[dict], totals: dict) -> str:
    """Human-readable 'Logged meal for <date>' style summary block."""
    lines = [f"Logged meal for {date.today().isoformat()}:", ""]
    lines.append(f"{'Food':<32}{'Estimated amount':<20}{'Calories':<10}")

    for it in report_items:
        n = it["nutrition"]
        cal = f"~{int(round(n['calories']))} kcal" if n else "N/A"
        amount = f"~{it['estimated_grams']:g}g"
        lines.append(f"{it['item']:<32}{amount:<20}{cal:<10}")

    lines.append("")
    lines.append(f"Estimated total: ~{int(round(totals['calories']))} kcal")

    sod_low, sod_high = _sodium_range(totals.get("sodium_mg", 0))
    lines.append(
        f"Approx macros: {int(round(totals['protein_g']))} g protein, "
        f"{int(round(totals['carbs_g']))} g carbs, {int(round(totals['fat_g']))} g fat, "
        f"~{int(sod_low)}-{int(sod_high)} mg sodium."
    )

    uncertain = _uncertain_items(report_items)
    if uncertain:
        cal_low, cal_high = _calorie_range(report_items, totals["calories"])
        uncertain_str = " and ".join(uncertain[:2])
        lines.append(
            f"The biggest uncertainty is the {uncertain_str} amount. "
            f"A lighter portion could be closer to {int(cal_low)} kcal, "
            f"while a richer version could be around {int(cal_high)} kcal."
        )

    unmatched = _unmatched_items(report_items)
    if unmatched:
        lines.append(
            f"Note: {len(unmatched)} item(s) could not be matched to nutrition data "
            f"and are excluded from the total above: {', '.join(unmatched)}."
        )

    summary = "\n".join(lines)
    print("\n" + summary + "\n")
    return summary


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_meal_image(image_path: str = None, image_base64: str = None) -> list[dict]:
    """Detect food items + estimated grams + confidence from a meal photo (path or base64)."""
    return analyze_meal_image_impl(image_path, image_base64)


@mcp.tool()
def lookup_nutrition(food_name: str) -> dict:
    """Look up per-100g nutrition + FDC ID for a food name via USDA FoodData Central."""
    return lookup_nutrition_impl(food_name)


@mcp.tool()
def track_meal(image_path: str = None, image_base64: str = None) -> dict:
    """Full pipeline: photo -> detect foods -> USDA lookup -> scale -> totals + table + summary."""
    detected = analyze_meal_image_impl(image_path, image_base64)

    report = []
    for d in detected:
        nutrition_info = lookup_nutrition_impl(d["item"])
        report.append({
            "item": d["item"],
            "estimated_grams": d["grams"],
            "confidence": d["confidence"],
            "fdc_id": nutrition_info["fdc_id"],
            "matched_description": nutrition_info["matched_description"],
            "usda_match_found": nutrition_info["found"],
            "nutrition": _scale(nutrition_info["per_100g"], d["grams"]),
        })
        if not nutrition_info["found"]:
            print(f"[track_meal] UNMATCHED: '{d['item']}' excluded from totals")

    logged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\nMeal logged at: {logged_at}")

    _print_item_table(report)
    totals = _sum_totals(report)
    table = _build_table(report)
    summary = _build_meal_summary(report, totals)

    low_confidence = [it["item"] for it in report if it["confidence"] == "low"]
    unmatched = _unmatched_items(report)

    return {
        "logged_at": logged_at,
        "items": report,
        "totals": totals,
        "needs_clarification": low_confidence,
        "unmatched_items": unmatched,
        "warning": f"{len(unmatched)} item(s) excluded from totals: {unmatched}" if unmatched else None,
        "table": table,
        "summary": summary,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, path="/mcp")