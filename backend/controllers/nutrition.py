"""Controller layer for estimate_meal_nutrition and log_meal."""

from typing import Annotated

from pydantic import Field

from mcp_app import mcp
from nutrition_tracker.store import log_meal_impl
from nutrition_tracker.tracking import estimate_meal_nutrition_impl
from views.input_coercion import coerce_dict_list
from views.responses import tool_error
from views.schemas import FOOD_ITEM_SCHEMA, MEAL_TYPE_FIELD


@mcp.tool()
def estimate_meal_nutrition(
    foods: Annotated[list[dict | str], Field(json_schema_extra={"items": FOOD_ITEM_SCHEMA})],
) -> dict:
    """Tool 4. Converts foods into nutrients — used by both the
    single-photo flow and the before/after flow's consumed-weight output.
    `foods` is a list of {"name": ..., "weight_g": ...} (also accepts
    "estimated_weight_g"/"consumed_weight_g", so analyze_meal/
    resolve_meal_clarification/analyze_meal_remaining output passes straight
    through; entries may also be JSON-encoded object strings). Runs
    normalize -> search FDC -> top-ranked result per provider -> scale by
    weight, returning {foods: [{name, calories, fdc_id, match_confidence,
    matched_description, source, source_id, sources}], nutrition: {calories,
    protein_g, carbohydrate_g, fat_g, fiber_g, sugar_g, sodium_mg,
    potassium_mg}}. `calories` is per-food; the other macros only live in
    the meal-wide totals. `source`/`source_id` is the primary matched
    provider + reference id (e.g. "usda" + FDC ID, "openfoodfacts" +
    barcode, "nutritionix" + item id, "indb" + food code); `sources` lists
    every provider that contributed. The only tool allowed to touch the
    nutrition pipeline — always call it, never estimate nutrition yourself."""
    if not foods:
        return tool_error("No foods provided.", "Call analyze_meal first.")
    try:
        parsed_foods = coerce_dict_list(foods, "foods")
    except ValueError as e:
        return tool_error(
            str(e),
            'Each food must be an object like {"name": "...", "weight_g": 100}, or that same object JSON-encoded as a string.',
        )
    return estimate_meal_nutrition_impl(parsed_foods)


@mcp.tool()
def log_meal(
    patient_id: str,
    timestamp: str,
    meal_type: Annotated[str, MEAL_TYPE_FIELD],
    foods: list[dict | str],
    nutrition: dict,
) -> dict:
    """Tool 5. Persists the meal (typically estimate_meal_nutrition's output
    plus patient_id/timestamp/meal_type). Each `foods` entry may also be a
    JSON-encoded object string. Returns {meal_id, status: "logged"}."""
    try:
        parsed_foods = coerce_dict_list(foods, "foods")
    except ValueError as e:
        return tool_error(str(e), "Each food must be an object, or a JSON-encoded object string.")
    return log_meal_impl(patient_id, timestamp, meal_type, parsed_foods, nutrition)
