"""
MCP Client — consume the Nexova MCP Server via Streamable HTTP transport.

This client is used by the LangGraph agent (``services/api/services/mcp_agent_adapter.py``)
to replace direct calls to the Incidents Manager and Inventory services with
calls through the MCP protocol.

Usage (standalone test):
    python -m mcps.nexova_mcp.mcp_client get_incident 1
    python -m mcps.nexova_mcp.mcp_client list_products --category hardware
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

logger = logging.getLogger("nexova_mcp.client")

# ── Ensure .env is loaded for JWT_SECRET_KEY ────────────────────────────
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8010/mcp")


def _get_token() -> str | None:
    """Return a JWT token from env, or None if not configured."""
    token = os.environ.get("MCP_TEST_TOKEN")
    if token:
        return token
    # Try to mint one if JWT_SECRET_KEY is available
    secret = os.environ.get("JWT_SECRET_KEY")
    if not secret:
        return None
    try:
        from mcps.nexova_mcp.token_issuer import mint_token
        return mint_token(
            sub="agent",
            scopes=["incidents:read", "incidents:write", "inventory:read"],
        )
    except Exception:
        return None


# ==========================================================================
#  MCP Client
# ==========================================================================

class NexovaMCPClient:
    """Async client that communicates with the Nexova MCP Server via Streamable HTTP."""

    def __init__(
        self,
        server_url: str = MCP_SERVER_URL,
        token: str | None = None,
        timeout: float = 10.0,
    ):
        self.server_url = server_url
        self._token = token or _get_token()
        self._timeout = timeout

    async def _make_http_client(self) -> "httpx2.AsyncClient":
        """Create an httpx2 client with auth headers."""
        import httpx2
        headers = {
            "User-Agent": "nexova-mcp-client/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx2.AsyncClient(
            headers=headers,
            timeout=httpx2.Timeout(self._timeout),
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Call an MCP tool and return its result.

        Parameters
        ----------
        tool_name : str
            Name of the tool to invoke.
        arguments : dict, optional
            Tool parameters as keyword-value pairs.

        Returns
        -------
        Any
            The tool's result content (parsed JSON or raw text).
        """
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        http_client = await self._make_http_client()
        transport_cm = streamable_http_client(url=self.server_url, http_client=http_client)

        async with transport_cm as (read_stream, write_stream):
            session = ClientSession(read_stream, write_stream)
            await session.initialize()
            result = await session.call_tool(
                tool_name,
                arguments=arguments or {},
            )
            # Parse content
            if result.content:
                texts = []
                for content_item in result.content:
                    texts.append(content_item.text if hasattr(content_item, 'text') else str(content_item))
                raw = "".join(texts)
                try:
                    return json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    return raw
            if result.isError:
                return {
                    "outcome": "error",
                    "message": f"Tool '{tool_name}' returned an error",
                }
            return {"outcome": "success", "result": str(result)}

    # ── Convenience wrappers (sync, for LangGraph nodes) ──────────────

    def call_tool_sync(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Synchronous wrapper around ``call_tool()``."""
        return asyncio.run(self.call_tool(tool_name, arguments))

    def get_incident(self, incident_id: int) -> dict[str, Any]:
        """Fetch a single incident by ID."""
        result = self.call_tool_sync("get_incident", {"incident_id": incident_id})
        if isinstance(result, dict):
            return result
        return {"outcome": "error", "message": "Unexpected response format"}

    def list_incidents(
        self,
        status: str | None = None,
        category: str | None = None,
        origin: str | None = None,
        branch: str | None = None,
    ) -> dict[str, Any]:
        """List incidents with optional filters."""
        args = {}
        if status:
            args["status"] = status
        if category:
            args["category"] = category
        if origin:
            args["origin"] = origin
        if branch:
            args["branch"] = branch
        result = self.call_tool_sync("list_incidents", args)
        if isinstance(result, list):
            return {"outcome": "found", "incidents": result}
        if isinstance(result, dict):
            return result
        return {"outcome": "error", "message": "Unexpected response format"}

    def get_product(
        self,
        product_id: int | None = None,
        sku: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a product by ID, SKU, or name."""
        args = {}
        if product_id is not None:
            args["product_id"] = product_id
        if sku:
            args["sku"] = sku
        if name:
            args["name"] = name
        result = self.call_tool_sync("get_product", args)
        if isinstance(result, dict):
            return result
        return {"outcome": "error", "message": "Unexpected response format"}

    def list_products(
        self,
        category: str | None = None,
        office: str | None = None,
    ) -> dict[str, Any]:
        """List products with optional filters."""
        args = {}
        if category:
            args["category"] = category
        if office:
            args["office"] = office
        result = self.call_tool_sync("list_products", args)
        if isinstance(result, list):
            return {"outcome": "found", "products": result}
        if isinstance(result, dict):
            return result
        return {"outcome": "error", "message": "Unexpected response format"}

    def create_incident(
        self,
        title: str,
        description: str,
        category: str,
        status: str,
        origin: str,
        branch: str,
    ) -> dict[str, Any]:
        """Create a new incident."""
        result = self.call_tool_sync("create_incident", {
            "title": title,
            "description": description,
            "category": category,
            "status": status,
            "origin": origin,
            "branch": branch,
        })
        if isinstance(result, dict):
            return result
        return {"outcome": "error", "message": "Unexpected response format"}


# ==========================================================================
#  CLI entry point
# ==========================================================================

async def _main() -> None:
    parser = argparse.ArgumentParser(description="Call a Nexova MCP tool.")
    parser.add_argument("tool", help="Tool name to invoke")
    parser.add_argument("args_json", nargs="?", help="JSON object of arguments")
    parser.add_argument("--server", default=MCP_SERVER_URL, help="MCP server URL")
    parser.add_argument("--token", help="Bearer token (or set MCP_TEST_TOKEN env)")
    args = parser.parse_args()

    token = args.token or os.environ.get("MCP_TEST_TOKEN")
    client = NexovaMCPClient(server_url=args.server, token=token)

    arguments = {}
    if args.args_json:
        arguments = json.loads(args.args_json)

    # Parse key=value positional arguments for convenience
    for arg in sys.argv:
        if "=" in arg and not arg.startswith("--"):
            k, v = arg.split("=", 1)
            # Try to parse int or float
            try:
                v = int(v)
            except ValueError:
                try:
                    v = float(v)
                except ValueError:
                    pass
            arguments[k] = v

    result = await client.call_tool(args.tool, arguments)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(_main())