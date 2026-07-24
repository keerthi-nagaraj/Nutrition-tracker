"""All schema/contract definitions for this server: tool-parameter wire formats AND Gemini's response schemas."""

from pydantic import Field

# analyze_meal's meal_type is coerced to "unknown" if it isn't one of these,
# rather than raising — never let a client-supplied enum value 500 the tool.
MEAL_TYPES = ["breakfast", "lunch", "dinner", "snack", "unknown"]

# Explicit enum, applied to every `meal_type` param below, so a bad value is
# rejected at the MCP boundary instead of silently coerced to "unknown" deep
# inside vision.py's _coerce_meal_type (kept as defense-in-depth, not a
# substitute for this — a schema hint doesn't guarantee every client honors it).
MEAL_TYPE_FIELD = Field(json_schema_extra={"enum": MEAL_TYPES})

# Explicit, fully-inlined item schemas for this server's list[dict] params —
# deliberately NOT Pydantic/TypedDict models. A bare `list[dict]` param
# schemas to {"type": "object"} with no declared `properties`, and a named
# model schemas via "$ref": "#/$defs/...". Gemini's function-calling schema
# (an OpenAPI-subset Schema proto) can't reliably target an underspecified
# object OR resolve $ref/$defs — both shapes make Gemini fall back to
# emitting each array item as a JSON-encoded string instead of a literal
# object. An inlined, fully-specified object schema is what it needs instead.
FOOD_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "weight_g": {"type": "number"},
        "estimated_weight_g": {"type": "number"},
        "consumed_weight_g": {"type": "number"},
    },
    "required": ["name"],
}
ANSWER_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "question_id": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["question_id", "answer"],
}


# ---------------------------------------------------------------------------
# Gemini structured-output schemas (formerly nutrition_tracker/schema.py)
# ---------------------------------------------------------------------------

LIGHTING = ["good", "fair", "poor"]
IMAGE_QUALITY = ["high", "medium", "low"]
CAMERA_ANGLE = ["top_down", "angled", "side", "unknown"]
REFERENCE_TYPE = ["fork", "knife", "spoon", "plate", "bowl", "cup", "glass", "hand", "packaging", "none"]
CONTAINER = ["plate", "bowl", "cup", "glass", "tray", "container", "package", "other"]
OCCLUSION = ["none", "partial", "major"]
PREPARATION = [
    "raw", "steamed", "boiled", "grilled", "fried", "roasted", "baked",
    "toasted", "sauteed", "mixed", "unknown",
]
APPLICATION = ["none", "drizzle", "spread", "dip", "coating", "mixed", "pool"]

_WEIGHT_RANGE = {
    "type": "object",
    "properties": {
        "min": {"type": "number"},
        "max": {"type": "number"},
    },
    "required": ["min", "max"],
}

_PORTION = {
    "type": "object",
    "properties": {
        "description": {"type": "string"},
        "estimated_weight_g": {"type": "number"},
        "weight_range_g": _WEIGHT_RANGE,
        "estimated_servings": {"type": "number"},
        "estimated_volume_ml": {"type": "number", "nullable": True},
        "fill_percentage": {"type": "number", "nullable": True},
    },
    "required": ["description", "estimated_weight_g", "weight_range_g"],
}

_VISIBILITY = {
    "type": "object",
    "properties": {
        "visible_fraction": {"type": "number"},
        "occlusion": {"type": "string", "enum": OCCLUSION},
        "cropped": {"type": "boolean"},
    },
    "required": ["visible_fraction", "occlusion", "cropped"],
}

_PROPERTIES = {
    "type": "object",
    "properties": {
        "liquid": {"type": "boolean"},
        "mixed_dish": {"type": "boolean"},
        "hidden_components_possible": {"type": "boolean"},
        "application": {"type": "string", "enum": APPLICATION},
    },
    "required": ["liquid", "mixed_dish", "hidden_components_possible", "application"],
}

_FOOD_CONFIDENCE = {
    "type": "object",
    "properties": {
        "food_identification": {"type": "number"},
        "portion_estimation": {"type": "number"},
    },
    "required": ["food_identification", "portion_estimation"],
}

_FOOD = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "fdc_search_hint": {"type": "string"},
        "preparation": {"type": "string", "enum": PREPARATION},
        "brand": {"type": "string", "nullable": True},
        "is_packaged": {"type": "boolean"},
        "container": {"type": "string", "enum": CONTAINER},
        "portion": _PORTION,
        "visibility": _VISIBILITY,
        "properties": _PROPERTIES,
        "confidence": _FOOD_CONFIDENCE,
    },
    "required": [
        "id", "name", "fdc_search_hint", "preparation", "is_packaged",
        "container", "portion", "visibility", "properties", "confidence",
    ],
}

QUESTION_TYPE = ["single_select"]

# `food_id` isn't in the original spec's clarification example, but without it
# resolve_meal_clarification has no way to know which food in a multi-food meal
# a given question_id's answer should correct — see nutrition_tracker/elicitation.py.
_QUESTION = {
    "type": "object",
    "properties": {
        "question_id": {"type": "string"},
        "food_id": {"type": "string"},
        "type": {"type": "string", "enum": QUESTION_TYPE},
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["question_id", "food_id", "type", "question", "options"],
}

_NEEDS_CONFIRMATION = {
    "type": "object",
    "properties": {
        "required": {"type": "boolean"},
        "questions": {"type": "array", "items": _QUESTION},
    },
    "required": ["required", "questions"],
}

ANALYSIS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {
            "type": "object",
            "properties": {
                "image_usable": {"type": "boolean"},
                "meal_visible": {"type": "boolean"},
                "meal_complete": {"type": "boolean"},
                "analysis_confidence": {"type": "number"},
            },
            "required": ["image_usable", "meal_visible", "meal_complete", "analysis_confidence"],
        },
        "scene": {
            "type": "object",
            "properties": {
                "lighting": {"type": "string", "enum": LIGHTING},
                "image_quality": {"type": "string", "enum": IMAGE_QUALITY},
                "camera_angle": {"type": "string", "enum": CAMERA_ANGLE},
                "multiple_containers": {"type": "boolean"},
            },
            "required": ["lighting", "image_quality", "camera_angle", "multiple_containers"],
        },
        "scale": {
            "type": "object",
            "properties": {
                "reference_type": {"type": "string", "enum": REFERENCE_TYPE},
                "reference_description": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": ["reference_type", "reference_description", "confidence"],
        },
        "foods": {"type": "array", "items": _FOOD},
        "needs_confirmation": _NEEDS_CONFIRMATION,
    },
    "required": ["analysis", "scene", "scale", "foods", "needs_confirmation"],
}

_COMPLETION_FOOD = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "fdc_search_hint": {"type": "string"},
        "consumed_weight_g": {"type": "number"},
        "confidence": {"type": "number"},
    },
    "required": ["id", "name", "fdc_search_hint", "consumed_weight_g", "confidence"],
}

# Tool 2 (analyze_meal_completion) — before/after comparison. Reuses
# _NEEDS_CONFIRMATION so the same clarification flow works for both tools.
COMPLETION_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {
            "type": "object",
            "properties": {"comparison_confidence": {"type": "number"}},
            "required": ["comparison_confidence"],
        },
        "foods": {"type": "array", "items": _COMPLETION_FOOD},
        "needs_confirmation": _NEEDS_CONFIRMATION,
    },
    "required": ["analysis", "foods", "needs_confirmation"],
}

_REMAINING_FOOD = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "remaining_weight_g": {"type": "number"},
        "confidence": {"type": "number"},
    },
    "required": ["name", "remaining_weight_g", "confidence"],
}

# Tool 2b (analyze_meal_remaining) — step two of the two-step before/after
# flow. Unlike COMPLETION_RESPONSE_SCHEMA (which compares two images in one
# call and has Gemini estimate consumed_weight_g directly), this is used
# with only the AFTER photo: Gemini is told what foods+weights were already
# detected in the BEFORE photo (see vision.py's call_remaining_vlm_raw) and
# just estimates each one's REMAINING weight — consumed weight is then
# computed in code (before - remaining), not guessed by the model. No
# needs_confirmation here: the food list is already fixed by the before
# analysis, so there's nothing to ask the user to disambiguate.
REMAINING_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "foods": {"type": "array", "items": _REMAINING_FOOD},
    },
    "required": ["foods"],
}
