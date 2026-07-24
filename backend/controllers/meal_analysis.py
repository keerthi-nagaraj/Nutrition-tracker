"""Controller layer for the photo-analysis tools: analyze_meal, analyze_meal_completion, analyze_meal_remaining, resolve_meal_clarification."""

from typing import Annotated, Any

from fastmcp import Context
from pydantic import Field

from mcp_app import mcp
from nutrition_tracker.elicitation import resolve_meal_clarification_impl
from nutrition_tracker.vision import analyze_meal_completion_impl, analyze_meal_impl, analyze_meal_remaining_impl
from views.input_coercion import coerce_dict_list, first_base64, resolve_image
from views.responses import tool_error
from views.schemas import ANSWER_ITEM_SCHEMA, MEAL_TYPE_FIELD

from .confirmation_flow import (
    MAX_ANALYZE_ROUNDS,
    clear_analysis_state,
    confirm_detected_foods,
    elicit_clarification_answers,
)


@mcp.tool()
async def analyze_meal(
    patient_id: str,
    meal_type: Annotated[str, MEAL_TYPE_FIELD],
    timestamp: str,
    ctx: Context,
    image: str | None = None,
    images: list[dict] | None = None,
) -> dict:
    """Tool 1. Analyzes a meal photo for foods and portions. `image`: file
    path or base64 string (optionally data:-prefixed); or `images:
    [{"base64": ...}]` (first entry used).
    Each food has `name` + `estimated_weight_g` — always state both to the
    user (e.g. "Steamed idli (~80g)").
    Ambiguous items (e.g. "whole milk or skim milk?") trigger MCP
    elicitation; if unsupported/declined, falls back to
    `needs_confirmation: {"required": true, "questions": [...]}` — ask
    those yourself and call resolve_meal_clarification with the answers
    before estimate_meal_nutrition.
    Then always tries to elicit full-list confirmation, returned as
    `user_confirmation`:
      - {"asked": false} — no elicitation support. YOU must show the full
        `foods` list (names + weights) and get explicit confirmation
        before estimate_meal_nutrition.
      - {"asked": true, "confirmed": true} — foods ready to use.
      - {"asked": true, "confirmed": false, "feedback": "..."} — human
        corrected something (e.g. "that's 200g not 100g"), saved
        server-side. Call analyze_meal AGAIN with the SAME arguments — do
        NOT apply the correction yourself or call resolve_meal_clarification.
        Repeat until confirmed=true or the round limit (then `foods` is
        the best attempt — resolve remaining doubts directly).
      - {"asked": true, "confirmed": false} — declined without feedback;
        ask what's wrong yourself.
    Never returns nutrition or a USDA ID — only estimate_meal_nutrition
    does."""

    resolved_image = image or first_base64(images)
    if not resolved_image:
        return tool_error(
            "No image provided.",
            "Pass `image` as a file path or base64 string, or `images` as [{'base64': ...}].",
        )

    # Retry state from a previous round of this same meal, if any.
    current_round = await ctx.get_state("round") or 0
    feedback = await ctx.get_state("feedback")
    previous_analysis_id = await ctx.get_state("analysis_id")
    previous_foods = await ctx.get_state("last_foods")

    if current_round >= MAX_ANALYZE_ROUNDS:
        result = {
            "analysis_id": previous_analysis_id,
            "foods": previous_foods or [],
            "needs_confirmation": {"required": False, "questions": []},
            "user_confirmation": {
                "asked": True,
                "confirmed": False,
                "feedback": feedback,
                "message": "Maximum correction attempts reached. Please manually review the detected foods.",
            },
        }
        await clear_analysis_state(ctx)
        return result

    try:
        result = analyze_meal_impl(
            patient_id, meal_type, timestamp, resolved_image, feedback=feedback, previous_foods=previous_foods
        )
    except (ValueError, FileNotFoundError) as e:
        return tool_error(
            str(e),
            "Check that `image` is a valid file path or base64 string; if it is, try a clearer, well-lit photo.",
        )

    analysis_id = result["analysis_id"]
    await ctx.set_state("analysis_id", analysis_id)

    # Ambiguous items (e.g. "whole milk or skim milk?") get resolved via
    # elicitation before the full-list confirmation below, if possible.
    needs_confirmation = result.get("needs_confirmation", {})
    if needs_confirmation.get("required") and needs_confirmation.get("questions"):
        answers = await elicit_clarification_answers(ctx, needs_confirmation["questions"])
        if answers is not None:
            resolved = resolve_meal_clarification_impl(analysis_id, answers)
            if resolved.get("error"):
                return resolved
            result = {
                "analysis_id": analysis_id,
                "foods": resolved["foods"],
                "needs_confirmation": {"required": False, "questions": []},
            }

    confirmation = await confirm_detected_foods(ctx, result.get("foods", []))
    result["user_confirmation"] = confirmation

    # Success path: user confirmed, or the client has no elicitation at all
    # (in which case the caller is responsible for confirming — see docstring).
    if not confirmation.get("asked") or confirmation.get("confirmed"):
        await clear_analysis_state(ctx)
        return result

    feedback = str(confirmation.get("feedback") or "").strip()
    if not feedback:
        return result  # declined without usable feedback — nothing to retry

    # Save retry state for the next analyze_meal call on this same meal.
    # analysis_id is already saved above and hasn't changed.
    await ctx.set_state("feedback", feedback)
    await ctx.set_state("round", current_round + 1)
    await ctx.set_state("last_foods", result.get("foods", []))

    return result


@mcp.tool()
def analyze_meal_completion(
    patient_id: str,
    meal_type: Annotated[str, MEAL_TYPE_FIELD],
    before_image: Any = None,
    after_image: Any = None,
    before_images: Any = None,
    after_images: Any = None,
    image: Any = None,
    images: Any = None,
) -> dict:
    """Tool 2. Compares BEFORE/AFTER photos of the same meal, estimates
    consumed weight per food. `before_image`/`after_image`: file path or
    base64 string (optionally data:-prefixed); or `before_images`/
    `after_images: [{"base64": ...}]` (first entry used). Returns {foods:
    [{name, consumed_weight_g, confidence}], needs_confirmation} — pass
    foods straight into estimate_meal_nutrition. Needs BOTH photos in one
    call; if you only have the AFTER photo + an analysis_id from
    analyze_meal, use analyze_meal_remaining instead."""
    resolved_before = resolve_image(before_image, before_images)
    # `image`/`images` carry no before/after signal on their own; some clients send only this
    # generic name for whichever photo they currently have — treat it as the AFTER photo (the
    # BEFORE photo, if missing, still triggers the clear error below rather than a crash).
    resolved_after = resolve_image(after_image, after_images, image, images)
    if not resolved_before or not resolved_after:
        return tool_error(
            "Both before_image and after_image are required.",
            "Pass each as a file path or base64 string, or as *_images: [{'base64': ...}]. "
            "If you only have the AFTER photo and an analysis_id from analyze_meal, use "
            "analyze_meal_remaining instead.",
        )
    try:
        return analyze_meal_completion_impl(patient_id, meal_type, resolved_before, resolved_after)
    except (ValueError, FileNotFoundError) as e:
        return tool_error(
            str(e), "Pass `before_image`/`after_image` as either a file path or a base64-encoded image string."
        )


@mcp.tool()
def analyze_meal_remaining(
    analysis_id: str,
    after_image: Any = None,
    after_images: Any = None,
    image: Any = None,
    images: Any = None,
) -> dict:
    """Tool 2b. Two-step alternative to analyze_meal_completion: call
    analyze_meal on the BEFORE photo alone first (returns analysis_id +
    foods + portions), confirm with the user, THEN call this with that
    analysis_id + the AFTER photo — it looks up the detected foods, asks
    Gemini each food's REMAINING weight, and computes consumed = before -
    remaining (never negative). `after_image`: file path or base64 string
    (optionally data:-prefixed); or `after_images: [{"base64": ...}]`;
    `image`/`images` are aliases for the same. Returns {foods: [{name,
    before_weight_g, after_weight_g, consumed_weight_g, confidence}]} — no
    calories/nutrients; feed consumed_weight_g into estimate_meal_nutrition."""
    resolved_after = resolve_image(after_image, image, after_images, images)
    if not resolved_after:
        return tool_error(
            "No after_image provided.",
            "Pass `after_image` as a file path or base64 string, or `after_images` as [{'base64': ...}].",
        )
    try:
        return analyze_meal_remaining_impl(analysis_id, resolved_after)
    except (ValueError, FileNotFoundError) as e:
        return tool_error(str(e), "Pass `after_image` as either a file path or a base64-encoded image string.")


@mcp.tool()
def resolve_meal_clarification(
    analysis_id: str,
    answers: Annotated[list[dict | str], Field(json_schema_extra={"items": ANSWER_ITEM_SCHEMA})],
) -> dict:
    """Tool 3. Applies user answers (each {"question_id": "q1", "answer":
    "Whole milk"}, or that object JSON-encoded as a string) to the
    `analysis_id` analysis (from analyze_meal) — no Gemini call. Returns
    {foods: [{name, estimated_weight_g}, ...]}, ready for
    estimate_meal_nutrition."""
    try:
        parsed_answers = coerce_dict_list(answers, "answers")
    except ValueError as e:
        return tool_error(
            str(e),
            'Each answer must be an object like {"question_id": "...", "answer": "..."}, or that same object JSON-encoded as a string.',
        )
    return resolve_meal_clarification_impl(analysis_id, parsed_answers)
