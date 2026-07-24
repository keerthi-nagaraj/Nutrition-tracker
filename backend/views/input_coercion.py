"""Normalizes tool inputs that some MCP clients send in slightly different shapes than this server's documented params."""

import json


def first_base64(images: list[dict] | None) -> str | None:
    """Fallback for clients that send `images: [{"base64": ...}, ...]` instead of a single image string."""
    if not images:
        return None
    first = images[0] or {}
    return first.get("base64") or first.get("data")


def resolve_image(*values) -> str | None:
    """Extracts a file path or base64 image string from whatever shape a client sent it in — a raw
    string, a dict with a `base64`/`data` key, or a list of either. Checked in order; first hit wins.
    Kept permissive (params typed loosely upstream) so a mis-shaped image never reaches pydantic
    validation, which would otherwise echo the raw payload into fastmcp's warning log."""
    for value in values:
        if not value:
            continue
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            found = value.get("base64") or value.get("data")
            if found:
                return found
        elif isinstance(value, list) and value:
            entry = value[0]
            if isinstance(entry, str):
                return entry
            if isinstance(entry, dict):
                found = entry.get("base64") or entry.get("data")
                if found:
                    return found
    return None


def coerce_dict_list(items: list[dict | str], param_name: str) -> list[dict]:
    """Normalizes each entry to a plain dict, also accepting a JSON-encoded string entry; raises ValueError otherwise."""
    coerced = []
    for i, item in enumerate(items):
        if isinstance(item, str):
            try:
                item = json.loads(item)
            except json.JSONDecodeError as e:
                raise ValueError(f"{param_name}[{i}] is a string but not valid JSON: {item!r} ({e})") from e
        if not isinstance(item, dict):
            raise ValueError(
                f"{param_name}[{i}] must be an object (or a JSON-encoded object string), got {type(item).__name__}"
            )
        coerced.append(item)
    return coerced
