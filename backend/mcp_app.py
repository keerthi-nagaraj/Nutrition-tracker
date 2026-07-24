"""Shared FastMCP instance that each controller module imports and registers its own tools on."""

import logging

from fastmcp import FastMCP

mcp = FastMCP("nutrition-tracker")


class _TruncateLongValues(logging.Filter):
    """fastmcp logs a raw dump of a tool call's arguments whenever pydantic validation fails
    (e.g. `logger.warning("Invalid arguments for tool %r: %s", name, cause.errors())`), and
    `ValidationError.errors()` always includes each field's full `input` value. For an image
    argument that means the entire base64 payload lands in the logs. Truncate any long string
    (recursively, through lists/dicts) before it's formatted into the log record."""

    MAX_LEN = 200

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._shorten(arg) for arg in record.args)
        return True

    def _shorten(self, value):
        if isinstance(value, str) and len(value) > self.MAX_LEN:
            return f"{value[: self.MAX_LEN]}...<truncated, {len(value)} chars total>"
        if isinstance(value, list):
            return [self._shorten(v) for v in value]
        if isinstance(value, dict):
            return {k: self._shorten(v) for k, v in value.items()}
        return value


for _logger_name in ("fastmcp", "mcp"):
    logging.getLogger(_logger_name).addFilter(_TruncateLongValues())
