"""
Nutrition Tracker MCP Server
============================

Pipeline (now split into two explicit stages so a user can confirm/edit
between them):

  STAGE 1 — detect only:
    photo -> Gemini Vision -> [{item, grams, confidence}, ...]
    Call `analyze_meal_image`. Show this list to the user. Let them confirm
    it's correct, or edit item names / grams before anything is tracked.

  STAGE 2 — track confirmed items:
    confirmed items -> USDA FoodData Central lookup (per-100g nutrients)
                     -> scale per-100g values by grams
                     -> sum totals across items
                     -> build terminal table + markdown table + summary
    Call `track_meal` with the (possibly edited) list from Stage 1.

Why split like this: this file has no UI of its own — it can't "ask the
user" anything. The confirm/edit step has to happen in whatever is talking
to the person (chat app, mobile UI, etc). That layer calls
`analyze_meal_image`, shows the result, waits for a yes/edit, then calls
`track_meal` with the confirmed list. `track_meal` can still be called with
just a photo (skips confirmation, old one-shot behavior) if you don't need
the confirm step.

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
USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_DETAIL_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
gemini_model = genai.GenerativeModel("gemini-3.5-flash")
mcp = FastMCP("nutrition-tracker")

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



VLM_PROMPT = """You are a nutrition estimation assistant. Look at this photo of a meal and
identify every distinct food or drink item visible, with an estimated portion size.

For EACH distinct item:

1. IDENTIFY THE FOOD
   - Name it specifically enough to be nutritionally meaningful (e.g. "grilled chicken
     breast" not just "meat"; "steamed white rice" not just "rice").
   - Treat sauces, dips, dressings, garnishes, and toppings as separate items if they
     are visually distinguishable and would meaningfully change the nutrition count
     (e.g. "ranch dressing", "melted cheese", "olive oil drizzle").
   - Don't merge multiple distinct foods into one entry (e.g. a burger's bun, patty,
     and cheese may need to stay separate if they're not a standard packaged item).

2. ESTIMATE THE PORTION IN GRAMS (or milliliters for drinks/liquids)
   Use whatever container or vessel is visible in the photo as your primary reference
   scale, in this order of preference:
     - Cups/mugs: a standard coffee mug ≈ 240-350 ml
     - Drinking glasses: a standard glass ≈ 350-450 ml
     - Bowls: a cereal/soup bowl ≈ 400-600 ml; a large serving bowl ≈ 700-1000 ml
     - Plates: a standard dinner plate ≈ 25-28 cm diameter; a side/bread plate ≈ 15-18 cm
     - Takeout containers, wrappers, boxes, or trays: use the known typical size for
       that packaging (e.g. a standard fast-food wrapper, a pint-sized takeout container)
     - Utensils/hands/common objects in frame (fork, spoon, coin, hand) as a fallback
       scale reference if no container is clearly visible
   If multiple items share one vessel (e.g. a bowl of rice and curry), estimate each
   item's share of that vessel's volume/depth separately, adjusting for density
   (a dense sauce weighs more per ml than a fluffy salad).
   State your best estimate even if the reference is imperfect — do not skip an item
   just because measurement is hard; instead, lower its confidence rating (see below).

3. RATE YOUR CONFIDENCE — high / medium / low
   - high: a whole, clearly visible, standard-shaped portion with a reliable size
     reference (e.g. a single grilled chicken breast on a plate)
   - medium: partially obscured, mixed into a dish, or an uncommon portion shape,
     but still reasonably estimable
   - low: liquid coatings, oils, sauces, dressings, melted cheese, garnishes, or
     anything where the true quantity is genuinely hard to judge visually

Do NOT include nutrition values (calories, macros, sodium, etc.) and do NOT include
any food database ID (such as a USDA FDC ID) — you do not have access to a nutrition
database and should not guess these. Only identify the item, its estimated grams, and
your confidence. Nutrition lookup and matching happens in a separate step outside of
your response.

Respond ONLY in this JSON format, no other text, no markdown code fences:
[
  {"item": "grilled chicken breast", "grams": 120, "confidence": "high"},
  {"item": "steamed white rice", "grams": 150, "confidence": "medium"},
]
"""


# ---------------------------------------------------------------------------
# Stage 1 — Image loading + Vision model (detection only, no tracking)
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
    """Photo -> Gemini -> [{item, grams, confidence}, ...]. Detection only —
    does NOT touch USDA or compute any nutrition. Show this to the user for
    confirmation before calling track_meal."""
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


def _format_for_confirmation(detected: list[dict]) -> str:
    """Human-readable list to show the user: 'Here's what I detected — is
    this right?' Used by whatever chat/UI layer is talking to the person."""
    lines = ["I detected the following in your photo:", ""]
    for it in detected:
        flag = "  (low confidence — please double-check)" if it["confidence"] == "low" else ""
        lines.append(f"  - {it['item']}: ~{it['grams']:g}g{flag}")
    lines.append("")
    lines.append("Is this correct? Reply to confirm, or tell me what to change "
                  "(item names, grams, or add/remove items) before I log it.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stage 2 — USDA lookup (only runs on CONFIRMED items)
# ---------------------------------------------------------------------------

def _best_match(food_name: str, candidates: list[dict]) -> dict:
    """Pick the candidate whose description is textually closest to
    `food_name`, instead of blindly trusting USDA's #1 ranked result.

    NOTE: only the final chosen match is surfaced anywhere (terminal or
    returned data) — the candidate pool and similarity scores used to get
    there are internal matching mechanics and are never shown or returned.
    """
    def score(candidate: dict) -> float:
        description = (candidate.get("description") or "").lower()
        return difflib.SequenceMatcher(None, food_name.lower(), description).ratio()

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0]
    print(f"[USDA] '{food_name}' -> FDC ID: {best['fdcId']} | {best.get('description')}")
    return best


def _simplify_query(food_name: str) -> str:
    """Strip filler words/qualifiers that make USDA's search choke on
    natural-language phrases, e.g. 'masala chai with milk and sugar'
    -> 'masala chai'. Keeps only the words before the first filler word.
    """
    fillers = (" with ", " and ", " in ", " on ", " topped ", " served ")
    lowered = food_name.lower()
    cut_at = len(food_name)
    for f in fillers:
        idx = lowered.find(f)
        if idx != -1:
            cut_at = min(cut_at, idx)
    simplified = food_name[:cut_at].strip()
    return simplified if simplified else food_name


def _usda_search(query: str) -> requests.Response | None:
    """Run one USDA search call. Returns the response, or None on failure
    (network error or non-2xx status) — never raises."""
    try:
        resp = requests.get(
            USDA_SEARCH_URL,
            params={
                "api_key": USDA_API_KEY,
                "query": query,
                "pageSize": USDA_CANDIDATE_COUNT,
                "dataType": ["Foundation", "SR Legacy", "Survey (FNDDS)"],
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        body = getattr(getattr(e, "response", None), "text", "")[:300]
        print(f"[USDA] WARNING: search failed for '{query}' — {e} | body: {body}")
        return None


def lookup_nutrition_impl(food_name: str) -> dict:
    """Food name -> USDA search + detail -> per-100g nutrients.

    Any USDA API failure (bad request, rate limit, network issue) is caught
    here and treated as 'not found' rather than crashing the whole tool
    call — one bad food name should never take down the rest of the meal.

    If the first search fails (USDA often rejects natural-language phrases
    like 'masala chai with milk and sugar'), retries once with a simplified
    query ('masala chai') before giving up.
    """
    if not USDA_API_KEY:
        raise RuntimeError("USDA_API_KEY not set")

    not_found = {
        "item": food_name, "fdc_id": None, "matched_description": None,
        "per_100g": None, "found": False,
    }

    search = _usda_search(food_name)

    if search is None:
        simplified = _simplify_query(food_name)
        if simplified != food_name:
            print(f"[USDA] Retrying with simplified query: '{simplified}'")
            search = _usda_search(simplified)
        if search is None:
            return not_found

    foods = search.json().get("foods", [])
    if not foods:
        print(f"[USDA] WARNING: no match found for '{food_name}' — nutrition unavailable")
        return not_found

    match = _best_match(food_name, foods)
    fdc_id, description = match["fdcId"], match.get("description")

    try:
        detail_resp = requests.get(
            USDA_DETAIL_URL.format(fdc_id=fdc_id),
            params={"api_key": USDA_API_KEY},
            timeout=15,
        )
        detail_resp.raise_for_status()
        detail = detail_resp.json()
    except requests.RequestException as e:
        print(f"[USDA] WARNING: detail lookup failed for FDC ID {fdc_id} — {e}")
        return not_found

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
# Scale per-100g values by estimated grams, then sum across items
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
# Uncertainty modeling
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
# Output builders (terminal table, markdown table, text summary)
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


def _track_confirmed_items(items: list[dict]) -> dict:
    """Shared logic: takes a list of {item, grams, confidence} and runs
    USDA lookup -> scale -> totals -> table -> summary. Used by both
    track_meal (one-shot) and track_confirmed_meal (post-confirmation)."""
    report = []
    for d in items:
        nutrition_info = lookup_nutrition_impl(d["item"])
        report.append({
            "item": d["item"],
            "estimated_grams": d["grams"],
            "confidence": d.get("confidence", "high"),
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


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_meal_image(image_path: str = None, image_base64: str = None) -> dict:
    """STAGE 1 — Detect food items + estimated grams + confidence from a
    meal photo. Does NOT log/track anything yet. Returns both the raw
    detected list and a ready-to-show confirmation message — show the
    message to the user, wait for their confirmation or edits, then call
    track_confirmed_meal with the (possibly edited) items."""
    try:
        detected = analyze_meal_image_impl(image_path, image_base64)
    except (ValueError, FileNotFoundError) as e:
        return {
            "error": True,
            "message": str(e),
            "hint": "Call this tool again with either image_path (a file path) "
                    "or image_base64 (a base64-encoded image string).",
        }
    return {
        "detected_items": detected,
        "confirmation_message": _format_for_confirmation(detected),
    }


@mcp.tool()
def lookup_nutrition(food_name: str) -> dict:
    """Look up per-100g nutrition + FDC ID for a food name via USDA FoodData Central."""
    try:
        return lookup_nutrition_impl(food_name)
    except RuntimeError as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def track_confirmed_meal(items: list[dict]) -> dict:
    """STAGE 2 — Track a meal from a USER-CONFIRMED list of items, each
    shaped like {"item": "chicken tenders", "grams": 150, "confidence": "high"}.
    Call this AFTER the user has confirmed or edited the output of
    analyze_meal_image. Runs USDA lookup -> scale -> totals -> table + summary."""
    if not items:
        return {"error": True, "message": "No items provided. Call analyze_meal_image first."}
    try:
        return _track_confirmed_items(items)
    except RuntimeError as e:
        return {"error": True, "message": str(e)}


@mcp.tool()
def track_meal(image_path: str = None, image_base64: str = None, confirmed: bool = False) -> dict:
    """Photo -> detect food items. Nutrition/calories/macros are ONLY
    computed and returned if `confirmed=True`.

    - confirmed=False (default): detects items and returns them plus a
      confirmation_message for the user to review — NO calories, macros,
      or totals are computed or included at this point.
    - confirmed=True: means the user has already reviewed and approved the
      detected items exactly as detected — only then does this run the
      USDA lookup and return calories/macros/totals.

    If the user wants to EDIT items before confirming (fix a wrong food
    name or portion), don't set confirmed=True here — instead call
    analyze_meal_image, let them edit the list, then call
    track_confirmed_meal with the corrected items.
    """
    try:
        detected = analyze_meal_image_impl(image_path, image_base64)
    except (ValueError, FileNotFoundError) as e:
        return {
            "error": True,
            "message": str(e),
            "hint": "Call this tool again with either image_path (a file path) "
                    "or image_base64 (a base64-encoded image string).",
        }

    if not confirmed:
        # Nutrition is deliberately withheld until the user confirms.
        return {
            "status": "awaiting_confirmation",
            "detected_items": detected,
            "confirmation_message": _format_for_confirmation(detected),
        }

    try:
        return _track_confirmed_items(detected)
    except RuntimeError as e:
        return {"error": True, "message": str(e)}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="127.0.0.1", port=8000, path="/mcp")