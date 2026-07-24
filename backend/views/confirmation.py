"""Renders the human-facing prompt for analyze_meal's full-list confirmation step."""

CONFIRM_YES = "Yes, this looks correct"
CONFIRM_NO = "No, something needs fixing"


def render_detected_foods_summary(foods: list[dict]) -> str:
    if not foods:
        return "No foods were detected."

    lines = []
    for food in foods:
        weight = food.get("estimated_weight_g") or food.get("consumed_weight_g") or food.get("weight_g")
        name = food.get("name", "Unknown food")
        lines.append(f"- {name}" if weight is None else f"- {name} (~{weight:g}g)")

    return "I detected:\n" + "\n".join(lines) + "\n\nDoes this look correct?"
