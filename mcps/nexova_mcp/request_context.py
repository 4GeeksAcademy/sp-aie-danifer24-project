"""Per-request authentication context shared by MCP tools."""

from contextvars import ContextVar

# Raw bearer token for downstream API calls made by the MCP tool implementation.
incoming_bearer_token: ContextVar[str | None] = ContextVar("incoming_bearer_token", default=None)

# Authenticated user's bearer token set by the API for the duration of an agent query.
api_bearer_token: ContextVar[str | None] = ContextVar("api_bearer_token", default=None)
