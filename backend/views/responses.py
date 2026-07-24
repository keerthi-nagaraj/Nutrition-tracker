"""Shared caller-facing error shape every tool returns on bad input."""


def tool_error(message: str, hint: str) -> dict:
    return {"error": True, "message": message, "hint": hint}
