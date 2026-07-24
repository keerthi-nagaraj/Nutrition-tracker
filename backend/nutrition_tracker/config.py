"""Env vars, API endpoints, and tunable constants shared across the vision and provider modules."""

import os

from dotenv import load_dotenv
import google.generativeai as genai

# MEAL_TYPES re-exported here (unused in this file itself) so vision.py's
# `from .config import ... MEAL_TYPES` keeps working unchanged.
from views.schemas import (  # noqa: F401
    ANALYSIS_RESPONSE_SCHEMA,
    COMPLETION_RESPONSE_SCHEMA,
    MEAL_TYPES,
    REMAINING_RESPONSE_SCHEMA,
)

load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# All three Gemini prompts (single-photo, before/after, remaining) live in
# this one file, delimited by `<!-- PROMPT: name -->` markers — see
# vision.py's _load_prompt_sections. Each is still a separate string sent to
# a differently-schema-constrained Gemini call; only the on-disk file count
# changed from three to one.
PROMPT_PATH = os.path.join(BACKEND_DIR, "prompt.md")

# Indian Nutrient Databank (INDB) — local CC-BY-licensed dataset, no API key
# or network call required. See nutrition_tracker/data/ATTRIBUTION.md.
INDB_CSV_PATH = os.path.join(PACKAGE_DIR, "data", "indb_nutrients.csv")

# Regional/cuisine food-name mapping (e.g. "dal" -> "cooked yellow lentils")
# used by normalization.py before FDC search — no API key or network call.
REGIONAL_MAP_CSV_PATH = os.path.join(PACKAGE_DIR, "data", "regional_food_map.csv")

# Local SQLite store for analyze_meal/analyze_meal_completion results (looked
# up by analysis_id in resolve_meal_clarification) and logged meals — see
# store.py. No existing persistence layer in this repo before this.
DB_PATH = os.path.join(PACKAGE_DIR, "data", "tracker.db")

USDA_API_KEY = os.getenv("USDA_API_KEY")
USDA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_DETAIL_URL = "https://api.nal.usda.gov/fdc/v1/food/{fdc_id}"
# "Branded Foods" included so brand-match scoring in providers.py has actual
# branded candidates to score against, per the FDC matching-strategy spec.
USDA_DATA_TYPES = ["Foundation", "SR Legacy", "Survey (FNDDS)", "Branded Foods"]

# Open Food Facts needs no API key — always available as a nutrition source.
OFF_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OFF_HEADERS = {"User-Agent": "nutrition-tracker-mcp/1.0"}

# Nutritionix is optional — only queried if both env vars below are set.
NUTRITIONIX_APP_ID = os.getenv("NUTRITIONIX_APP_ID")
NUTRITIONIX_APP_KEY = os.getenv("NUTRITIONIX_APP_KEY")
NUTRITIONIX_NATURAL_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Structured output: the model is forced to match ANALYSIS_RESPONSE_SCHEMA
# (enums, required fields, and types enforced by the API) instead of relying
# on prompt text alone to shape the reply — see views/schemas.py.
gemini_model = genai.GenerativeModel(
    "gemini-3.1-flash-lite",
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=ANALYSIS_RESPONSE_SCHEMA,
    ),
)

# Same model, but constrained to COMPLETION_RESPONSE_SCHEMA for the before/after
# (analyze_meal_completion) tool — see vision.py's call_completion_vlm_raw.
gemini_completion_model = genai.GenerativeModel(
    "gemini-3.1-flash-lite",
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=COMPLETION_RESPONSE_SCHEMA,
    ),
)

# Same model, but constrained to REMAINING_RESPONSE_SCHEMA for the two-step
# before/after flow's second step (analyze_meal_remaining) — see vision.py's
# call_remaining_vlm_raw. Only ever sent ONE image (the after photo); the
# before photo's foods/weights are passed in as text, not a second image.
gemini_remaining_model = genai.GenerativeModel(
    "gemini-3.1-flash-lite",
    generation_config=genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=REMAINING_RESPONSE_SCHEMA,
    ),
)

# USDA nutrient name -> short key used throughout the provider/tracking modules.
# USDA reports sugar under different names depending on dataType: SR Legacy/
# Foundation use "Sugars, total including NLEA", while Survey (FNDDS) — the
# dataType most current searches match — uses "Total Sugars". Both map to the
# same sugar_g key so neither dataType silently reports 0g sugar. Field names
# below (carbohydrate_g, potassium_mg) match estimate_meal_nutrition's response.
NUTRIENTS = {
    "Energy": "calories",
    "Protein": "protein_g",
    "Carbohydrate, by difference": "carbohydrate_g",
    "Total lipid (fat)": "fat_g",
    "Fiber, total dietary": "fiber_g",
    "Sugars, total including NLEA": "sugar_g",
    "Total Sugars": "sugar_g",
    "Sodium, Na": "sodium_mg",
    "Potassium, K": "potassium_mg",
}

# How much each confidence level should widen the calorie estimate range.
# Low-confidence items (oils, sauces, cheese) swing the total far more
# than high-confidence items (a whole grilled chicken breast, etc).
CONFIDENCE_VARIANCE = {"low": 0.35, "medium": 0.20, "high": 0.05}

# Sodium is one of the least reliable values to estimate visually
# (dressings, added salt, oil), so it's always reported as a range.
SODIUM_RANGE_FACTORS = (0.85, 1.30)

# How much weight a provider's text-match quality vs. its data completeness
# gets when merging/labeling nutrition results across providers.
MATCH_SCORE_WEIGHT = 0.7
COMPLETENESS_WEIGHT = 0.3

# Below this plain text-match score, providers.py's USDA lookup falls back to
# a broader/generic search (e.g. "grilled skinless chicken breast" ->
# "chicken breast") rather than accepting a weak match at face value.
FDC_MATCH_THRESHOLD = 0.5
