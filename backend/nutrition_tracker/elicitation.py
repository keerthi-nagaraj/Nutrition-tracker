"""Tool 3 model logic: applies the user's clarification answers to a prior analyze_meal analysis WITHOUT calling Gemini again."""

from . import store


def _error(message: str) -> dict:
    return {
        "error": True,
        "message": message,
        "hint": "Call analyze_meal first and use the analysis_id it returns.",
    }


def _weight_of(food: dict) -> float:
    portion = food.get("portion") or {}
    return portion.get("estimated_weight_g", food.get("consumed_weight_g", 0))


def resolve_meal_clarification_impl(analysis_id: str, answers: list[dict]) -> dict:
    """Applies each answer's question_id -> food_id match to overwrite that food's name, returning the FULL corrected meal."""
    record = store.get_analysis(analysis_id)
    if record is None:
        return _error(f"No analysis found for analysis_id={analysis_id!r}.")

    foods = record["foods"]
    foods_by_id = {f.get("id"): f for f in foods}
    questions_by_id = {q.get("question_id"): q for q in record["needs_confirmation"].get("questions", [])}

    for answer in answers:
        question_id = answer.get("question_id")
        question = questions_by_id.get(question_id)
        if question is None:
            print(f"[resolve_meal_clarification] WARNING: unknown question_id {question_id!r} — skipped")
            continue

        food_id = question.get("food_id")
        food = foods_by_id.get(food_id)
        if food is None:
            print(
                f"[resolve_meal_clarification] WARNING: question {question_id!r} references "
                f"unknown food_id {food_id!r} — skipped"
            )
            continue

        food["name"] = answer.get("answer", food.get("name"))

    return {
        "foods": [{"name": f.get("name", "unknown"), "estimated_weight_g": _weight_of(f)} for f in foods]
    }
