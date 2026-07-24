"""Model logic for Tools 1/2/2b: image loading + Gemini calls, never touching the nutrition pipeline."""

import os
import re
import json
import base64
import mimetypes
import uuid
from datetime import datetime, timezone

from . import store
from .config import PROMPT_PATH, gemini_model, gemini_completion_model, gemini_remaining_model, MEAL_TYPES

_SECTION_RE = re.compile(r"<!--\s*PROMPT:\s*(\w+)\s*-->\n?")


def _load_prompt_sections(path: str) -> dict[str, str]:
    """Splits one file into named sections delimited by `<!-- PROMPT: name -->` markers."""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    parts = _SECTION_RE.split(text)
    return {name: content.strip() for name, content in zip(parts[1::2], parts[2::2])}


_PROMPTS = _load_prompt_sections(PROMPT_PATH)
VLM_PROMPT = _PROMPTS["single_photo"]
COMPLETION_PROMPT = _PROMPTS["before_after"]
REMAINING_PROMPT = _PROMPTS["remaining"]


def _resolve_image(image: str) -> tuple[bytes, str]:
    """Loads image bytes + mime type from a file path or a base64 (optionally data-URI-prefixed) string."""
    if not image:
        raise ValueError("Provide `image` as a file path or base64 string.")

    if not image.startswith("data:") and os.path.exists(image):
        media_type = mimetypes.guess_type(image)[0] or "image/jpeg"
        with open(image, "rb") as f:
            return f.read(), media_type

    if image.startswith("data:"):
        header, _, image = image.partition(",")
        media_type = (re.match(r"data:(image/\w+);base64", header) or [None, "image/jpeg"])[1]
    else:
        media_type = "image/jpeg"
    return base64.b64decode(image), media_type


def _coerce_meal_type(meal_type: str | None) -> str:
    """Coerces anything outside MEAL_TYPES to 'unknown' instead of raising."""
    if meal_type in MEAL_TYPES:
        return meal_type
    print(f"[analyze_meal] WARNING: unrecognized meal_type {meal_type!r} — coerced to 'unknown'")
    return "unknown"


def _render_foods_list(foods: list[dict], header: str, approximate: bool = False) -> str:
    """Renders foods as "- name: weightg" lines under a header, for appending to a Gemini prompt."""
    prefix = "~" if approximate else ""
    lines = [f"- {f.get('name', 'unknown')}: {prefix}{f.get('estimated_weight_g', 0):g}g" for f in foods]
    return f"{header}\n" + "\n".join(lines)


_JSON_RETRY_NOTE = (
    "\n\n---\n\nYour previous reply was not valid JSON matching the required "
    "schema. Return ONLY valid JSON this time — no prose, no markdown fences."
)


def call_vlm_raw(
    image: str, feedback: str | None = None, previous_foods: list[dict] | None = None, retry: bool = False
) -> str:
    """image -> Gemini -> raw text reply; `feedback`/`previous_foods` (if given) steer a correction re-analysis."""
    image_bytes, media_type = _resolve_image(image)
    prompt = VLM_PROMPT
    if feedback:
        prompt = (
            f"{VLM_PROMPT}\n\n---\n\nA human already reviewed a previous analysis "
            f"of this exact photo and said the following needs fixing — "
            f"incorporate this correction into your analysis:\n\n{feedback}"
        )
        if previous_foods:
            foods_list = _render_foods_list(previous_foods, "Foods from your previous analysis of this photo:", approximate=True)
            prompt += (
                f"\n\n{foods_list}"
                f"\n\nKeep every food from that previous analysis in your response "
                f"UNLESS the correction above says to remove, replace, or merge it. "
                f"Only change what the correction actually addresses — do not drop, "
                f"rename, or re-estimate other foods that weren't mentioned."
            )
    if retry:
        prompt += _JSON_RETRY_NOTE
    return gemini_model.generate_content(
        [{"mime_type": media_type, "data": image_bytes}, prompt]
    ).text


def call_completion_vlm_raw(before_image: str, after_image: str, retry: bool = False) -> str:
    """before/after images -> Gemini -> raw text reply, both images sent labeled in one call."""
    before_bytes, before_type = _resolve_image(before_image)
    after_bytes, after_type = _resolve_image(after_image)
    prompt = COMPLETION_PROMPT + (_JSON_RETRY_NOTE if retry else "")
    return gemini_completion_model.generate_content(
        [
            "BEFORE eating:",
            {"mime_type": before_type, "data": before_bytes},
            "AFTER eating:",
            {"mime_type": after_type, "data": after_bytes},
            prompt,
        ]
    ).text


def call_remaining_vlm_raw(after_image: str, before_foods: list[dict], retry: bool = False) -> str:
    """AFTER image + BEFORE foods/weights -> Gemini -> raw text reply; only ONE image is sent."""
    image_bytes, media_type = _resolve_image(after_image)
    foods_list = _render_foods_list(before_foods, "Foods from the BEFORE photo (name: served weight in grams):")
    prompt = REMAINING_PROMPT + "\n\n" + foods_list + (_JSON_RETRY_NOTE if retry else "")
    return gemini_remaining_model.generate_content(
        [{"mime_type": media_type, "data": image_bytes}, prompt]
    ).text


def parse_vlm_analysis(reply: str) -> dict:
    """Raw model text -> parsed dict, with a defensive brace-extraction fallback if it's wrapped in prose/fences."""
    try:
        return json.loads(reply)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", reply, re.DOTALL)
        if not match:
            raise ValueError(f"No JSON object found in model output: {reply[:200]}")
        return json.loads(match.group(0))


def _parse_with_retry(call_fn) -> dict:
    """Calls call_fn(retry: bool) -> parse; on malformed JSON, retries once with a corrective prompt before giving up."""
    try:
        return parse_vlm_analysis(call_fn(False))
    except ValueError:
        print("[vision] WARNING: malformed JSON from Gemini — retrying once with a corrective prompt.")
        return parse_vlm_analysis(call_fn(True))


def _empty_needs_confirmation() -> dict:
    return {"required": False, "questions": []}


def _reject_invalid_weights(foods: list[dict], weight_key: str, *, nested_in: str | None = None) -> list[dict]:
    """Drops any food whose weight is missing, zero, or negative — never invent a value for it."""
    valid = []
    for food in foods:
        source = (food.get(nested_in) or {}) if nested_in else food
        weight = source.get(weight_key)
        if not isinstance(weight, (int, float)) or weight <= 0:
            print(f"[vision] WARNING: dropping {food.get('name', 'unknown')!r} — invalid weight {weight!r}")
            continue
        valid.append(food)
    return valid


def flatten_food(food: dict) -> dict:
    """One raw Gemini-analysis food -> the flat shape both analyze_meal_impl and batch_process_images.py need."""
    portion = food.get("portion") or {}
    return {
        "name": food.get("name", "unknown"),
        "fdc_search_hint": food.get("fdc_search_hint") or food.get("name", "unknown"),
        "estimated_weight_g": portion.get("estimated_weight_g", 0),
        "weight_range_g": portion.get("weight_range_g") or {"min": None, "max": None},
        "confidence": food.get("confidence") or {"food_identification": 0, "portion_estimation": 0},
    }


def analyze_meal_impl(
    patient_id: str,
    meal_type: str,
    timestamp: str,
    image: str,
    feedback: str | None = None,
    previous_foods: list[dict] | None = None,
) -> dict:
    """Tool 1 model logic: runs Gemini detection, persists it under a new analysis_id, returns foods + needs_confirmation."""
    meal_type = _coerce_meal_type(meal_type)
    analysis = _parse_with_retry(
        lambda retry: call_vlm_raw(image, feedback=feedback, previous_foods=previous_foods, retry=retry)
    )

    scene_analysis = analysis.get("analysis") or {}
    if scene_analysis.get("image_usable") is False:
        raise ValueError("Image quality too poor for a reliable estimate — please retake the photo.")

    foods = _reject_invalid_weights(analysis.get("foods", []), "estimated_weight_g", nested_in="portion")
    if not foods and scene_analysis.get("meal_visible") is not False:
        raise ValueError("No foods detected, but the model did not report the meal as not visible — try a clearer photo.")

    needs_confirmation = analysis.get("needs_confirmation") or _empty_needs_confirmation()
    analysis_id = uuid.uuid4().hex

    store.save_analysis(
        analysis_id=analysis_id,
        patient_id=patient_id,
        meal_type=meal_type,
        kind="meal",
        foods=foods,
        needs_confirmation=needs_confirmation,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    response_foods = [flatten_food(food) for food in foods]

    return {
        "analysis_id": analysis_id,
        "foods": response_foods,
        "needs_confirmation": needs_confirmation,
    }


def analyze_meal_completion_impl(patient_id: str, meal_type: str, before_image: str, after_image: str) -> dict:
    """Tool 2 model logic: before/after photos -> Gemini comparison -> consumed_weight_g per food."""
    meal_type = _coerce_meal_type(meal_type)
    analysis = _parse_with_retry(lambda retry: call_completion_vlm_raw(before_image, after_image, retry=retry))

    foods = _reject_invalid_weights(analysis.get("foods", []), "consumed_weight_g")
    needs_confirmation = analysis.get("needs_confirmation") or _empty_needs_confirmation()

    store.save_analysis(
        analysis_id=uuid.uuid4().hex,
        patient_id=patient_id,
        meal_type=meal_type,
        kind="completion",
        foods=foods,
        needs_confirmation=needs_confirmation,
        created_at=datetime.now(timezone.utc).isoformat(),
    )

    response_foods = [
        {
            "name": f.get("name", "unknown"),
            "consumed_weight_g": f.get("consumed_weight_g", 0),
            "confidence": f.get("confidence", 0),
        }
        for f in foods
    ]

    return {"foods": response_foods, "needs_confirmation": needs_confirmation}


def analyze_meal_remaining_impl(analysis_id: str, after_image: str) -> dict:
    """Tool 2b model logic: looks up the BEFORE analysis, asks Gemini each food's REMAINING weight, computes consumed here."""
    record = store.get_analysis(analysis_id)
    if record is None:
        return {
            "error": True,
            "message": f"No analysis found for analysis_id={analysis_id!r}.",
            "hint": "Call analyze_meal on the BEFORE photo first and use the analysis_id it returns.",
        }

    before_foods = [flatten_food(food) for food in record["foods"]]
    if not before_foods:
        return {
            "error": True,
            "message": "The stored before-analysis has no foods to compare against.",
            "hint": "Call analyze_meal on the BEFORE photo first.",
        }

    analysis = _parse_with_retry(lambda retry: call_remaining_vlm_raw(after_image, before_foods, retry=retry))
    remaining_by_name = {f.get("name", "").lower(): f for f in analysis.get("foods", [])}

    result_foods = []
    for before in before_foods:
        remaining = remaining_by_name.get(before["name"].lower())
        before_weight = before["estimated_weight_g"]
        after_weight = remaining.get("remaining_weight_g", 0) if remaining else 0
        result_foods.append({
            "name": before["name"],
            "before_weight_g": before_weight,
            "after_weight_g": after_weight,
            "consumed_weight_g": max(before_weight - after_weight, 0),
            "confidence": remaining.get("confidence", 0) if remaining else 0,
        })

    return {"foods": result_foods}
