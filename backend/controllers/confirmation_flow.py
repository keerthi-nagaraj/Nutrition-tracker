"""MCP elicitation orchestration for analyze_meal's human-in-the-loop confirmation flow."""

from fastmcp import Context
from fastmcp.server.elicitation import AcceptedElicitation
from mcp.shared.exceptions import McpError
from mcp.types import ClientCapabilities, ElicitationCapability

from views.confirmation import CONFIRM_NO, CONFIRM_YES, render_detected_foods_summary

# analyze_meal re-runs Gemini with the human's feedback at most this many
# extra times before giving up and returning the last (still-unconfirmed)
# attempt — bounds the loop if the human keeps rejecting corrections.
MAX_ANALYZE_ROUNDS = 3


def log_elicit_error(label: str, e: Exception) -> None:
    """Logs exception type + McpError's error code, since str(e) alone can misleadingly echo our own prompt text back."""
    if isinstance(e, McpError):
        print(f"[analyze_meal] {label}: McpError code={e.error.code} message={e.error.message!r}")
    else:
        import traceback
        print(f"[analyze_meal] {label}: {type(e).__name__}: {e}")
        traceback.print_exc()


def client_supports_elicitation(ctx: Context) -> bool:
    """Checks the client's declared capabilities up front, skipping a doomed elicit() round trip entirely."""
    return ctx.session.check_client_capability(ClientCapabilities(elicitation=ElicitationCapability()))


async def elicit_clarification_answers(ctx: Context, questions: list[dict]) -> list[dict] | None:
    """Asks each clarification question via MCP elicitation; returns answers, or None if unavailable/declined/invalid."""
    if not client_supports_elicitation(ctx):
        print("[analyze_meal] Client did not declare elicitation capability — falling back to needs_confirmation.")
        return None

    answers = []
    for q in questions:
        try:
            response = await ctx.elicit(q["question"], response_type=q["options"])
        except Exception as e:
            log_elicit_error("Elicitation unavailable — falling back to needs_confirmation", e)
            return None

        if not isinstance(response, AcceptedElicitation):
            print(f"[analyze_meal] Clarification declined/cancelled for {q['question_id']!r} — falling back.")
            return None

        answer = str(response.data).strip()

        # Validate against allowed options (case-insensitive), preserving
        # the option's original casing in the stored answer.
        allowed = q.get("options")
        if isinstance(allowed, list):
            normalized_allowed = {str(option).strip().lower(): option for option in allowed}
            normalized_answer = answer.strip().lower()
            if normalized_answer not in normalized_allowed:
                print(
                    f"[analyze_meal] Invalid clarification answer {answer!r} for question "
                    f"{q['question_id']!r}. Allowed: {allowed}"
                )
                return None
            answer = normalized_allowed[normalized_answer]

        answers.append({"question_id": q["question_id"], "answer": answer})

    return answers


async def confirm_detected_foods(ctx: Context, foods: list[dict]) -> dict:
    """Asks the human to confirm the full detected food list; returns {asked, confirmed[, feedback]} (see analyze_meal)."""
    if not foods:
        return {"asked": False}

    if not client_supports_elicitation(ctx):
        print("[analyze_meal] Client did not declare elicitation capability — caller must ask instead.")
        return {"asked": False}

    message = render_detected_foods_summary(foods)
    try:
        response = await ctx.elicit(message, response_type=[CONFIRM_YES, CONFIRM_NO])
    except Exception as e:
        log_elicit_error("Confirmation elicitation unavailable — caller must ask instead", e)
        return {"asked": False}

    if not isinstance(response, AcceptedElicitation):
        return {"asked": True, "confirmed": False}  # declined/cancelled

    if response.data == CONFIRM_YES:
        return {"asked": True, "confirmed": True}

    if response.data != CONFIRM_NO:
        print(f"[analyze_meal] Unexpected confirmation response: {response.data!r}")
        return {"asked": True, "confirmed": False}

    # User wants to make corrections.
    try:
        feedback_response = await ctx.elicit("What should be corrected?", response_type=str)
    except Exception as e:
        log_elicit_error("Feedback elicitation unavailable", e)
        return {"asked": True, "confirmed": False}

    if not isinstance(feedback_response, AcceptedElicitation):
        return {"asked": True, "confirmed": False}

    feedback = str(feedback_response.data).strip()
    if not feedback:
        print("[analyze_meal] User requested corrections but did not provide any feedback.")
        return {"asked": True, "confirmed": False}

    return {"asked": True, "confirmed": False, "feedback": feedback}


async def clear_analysis_state(ctx: Context) -> None:
    """Resets the per-session retry state once a meal's foods are settled, so the next analyze_meal call starts clean."""
    for key in ("round", "feedback", "analysis_id", "last_foods"):
        await ctx.delete_state(key)
