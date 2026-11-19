"""
MCP Client — consume the Nexova MCP Server via Streamable HTTP (SSE + POST).

Uses raw httpx2 instead of the mcp SDK (mcp SDK 2.3.0 has a compatibility bug
with FastMCP 4.2.0: it treats a 202 Accepted response to initialize as an error).

The public API is identical to the previous SDK-based version:
    client = NexovaMCPClient()
    result = client.call_tool_sync("get_incident", {"incident_id": 1})

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
import re
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from mcps.nexova_mcp.request_context import api_bearer_token

logger = logging.getLogger("nexova_mcp.client")

# ── Ensure .env is loaded for JWT_SECRET_KEY ────────────────────────────
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://localhost:8010/sse")


def _get_token() -> str | None:
    """Return the authenticated API user's token for the current request."""
    return api_bearer_token.get()


# ==========================================================================
#  Minimal SSE-based MCP client (no SDK dependency)
# ==========================================================================


class _SSEMCPClient:
    """Low-level async MCP client over SSE + POST.

    Holds a single SSE connection for its lifetime.  Sends requests via POST to
    ``/messages/?session_id=...``.  Responses arrive as SSE events on the same
    stream.
    """

    def __init__(
        self,
        server_url: str,
        http_client: "httpx2.AsyncClient",
        *,
        request_timeout: float = 30.0,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._client = http_client
        self._request_timeout = request_timeout
        self._session_id: str | None = None
        self._initialized = False

        # SSE reading machinery
        self._sse_aiter: AsyncIterator[bytes] | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._sse_buffer = ""
        self._reader_task: asyncio.Task | None = None

    async def __aenter__(self) -> _SSEMCPClient:
        await self._start_sse()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass

    async def _start_sse(self) -> None:
        """Open the SSE connection, extract session_id, start background reader."""
        response = await self._client.send(
            self._client.build_request("GET", self._server_url),
            stream=True,
        )
        self._sse_aiter = response.aiter_bytes()

        # Read until we get session_id
        async for chunk in self._sse_aiter:
            text = chunk.decode()
            self._sse_buffer += text
            m = re.search(r"/messages/\?session_id=([\w-]+)", self._sse_buffer)
            if m:
                self._session_id = m.group(1)
                logger.info("SSE session_id=%s", self._session_id)
                break

        # Start background reader (processes whatever remains & future events)
        self._reader_task = asyncio.create_task(self._sse_reader())

    async def _sse_reader(self) -> None:
        """Background: read SSE events and resolve pending futures."""
        try:
            async for chunk in self._sse_aiter:
                self._sse_buffer += chunk.decode()
                self._flush_sse_buffer()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("SSE reader error: %s", exc)

    def _flush_sse_buffer(self) -> None:
        """Parse buffered SSE text and resolve any pending futures."""
        while "\n" in self._sse_buffer:
            line, rest = self._sse_buffer.split("\n", 1)
            self._sse_buffer = rest
            line = line.strip()
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    msg_id = data.get("id")
                    if msg_id is not None:
                        fut = self._pending.get(msg_id)
                        if fut and not fut.done():
                            fut.set_result(data)
                        else:
                            logger.debug("No pending future for id=%s", msg_id)
                except json.JSONDecodeError:
                    pass

    def _messages_url(self) -> str:
        assert self._session_id is not None, "Not connected"
        base = self._server_url
        if base.endswith("/sse"):
            base = base[: -len("/sse")]
        return f"{base}/messages/?session_id={self._session_id}"

    async def initialize(self) -> dict[str, Any]:
        """Send initialize and wait for response via SSE."""
        result = await self._request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "nexova-mcp-client", "version": "1.0"},
            },
        )
        self._initialized = True
        return result

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self._request("tools/list", None)
        return result.get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
        )

    async def _request(self, method: str, params: Any | None) -> dict[str, Any]:
        """Send a JSON-RPC request, wait for SSE response."""
        msg_id = abs(hash((method, json.dumps(params, sort_keys=True)))) % 10_000_000
        body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "id": msg_id,
        }
        if params is not None:
            body["params"] = params

        # Register future BEFORE sending
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending[msg_id] = future

        try:
            # Send via POST
            logger.info("Sending %s (id=%s)", method, msg_id)
            post_resp = await self._client.post(
                self._messages_url(),
                json=body,
            )

            if post_resp.status_code == 405:
                raise RuntimeError(
                    f"POST to {self._messages_url()} returned 405. "
                    "Check server uses transport='sse'."
                )
            if post_resp.status_code == 202:
                logger.info("POST returned 202 — awaiting SSE response...")
            elif post_resp.status_code in (200, 201):
                try:
                    data = post_resp.json()
                    if data.get("id") == msg_id:
                        if "error" in data:
                            err = data["error"]
                            raise RuntimeError(
                                f"MCP error ({err.get('code')}): {err.get('message')}"
                            )
                        return data.get("result", data)
                except Exception:
                    raise RuntimeError(
                        f"POST returned {post_resp.status_code}: {post_resp.text[:500]}"
                    )
            else:
                raise RuntimeError(
                    f"POST returned {post_resp.status_code}: {post_resp.text[:500]}"
                )

            # Wait for SSE response
            try:
                data = await asyncio.wait_for(future, timeout=self._request_timeout)
            except asyncio.TimeoutError:
                raise RuntimeError(f"Timeout waiting for response to {method}")

            if "error" in data:
                err = data["error"]
                raise RuntimeError(
                    f"MCP error ({err.get('code')}): {err.get('message')}"
                )
            return data.get("result", data)

        finally:
            self._pending.pop(msg_id, None)

    async def notify(self, method: str, params: Any | None = None) -> None:
        """Send a JSON-RPC notification (fire-and-forget)."""
        body: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            body["params"] = params
        await self._client.post(self._messages_url(), json=body)


# ==========================================================================
#  NexovaMCPClient — same public API as before
# ==========================================================================


class NexovaMCPClient:
    """Async MCP client that talks to the Nexova MCP Server via raw SSE+POST.

    Usage:

        client = NexovaMCPClient()
        result = await client.call_tool("get_incident", {"incident_id": 1})

    Synchronous convenience wrappers are also provided:
        client.get_incident(1)
        client.list_incidents(status="open")
        ...
    """

    def __init__(
        self,
        server_url: str = MCP_SERVER_URL,
        token: str | None = None,
        timeout: float = 30.0,
    ):
        self.server_url = server_url
        self._token = token or _get_token()
        self._timeout = timeout

    async def _make_http_client(self) -> "httpx2.AsyncClient":
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

    async def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
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
        async with await self._make_http_client() as http_client:
            async with _SSEMCPClient(
                self.server_url, http_client, request_timeout=self._timeout
            ) as sse_client:
                await sse_client.initialize()
                await sse_client.notify("notifications/initialized")
                result = await sse_client.call_tool(tool_name, arguments or {})

        # Parse content
        content = result.get("content", [])
        if content:
            texts = []
            for content_item in content:
                texts.append(
                    content_item.get("text", "")
                    if isinstance(content_item, dict)
                    else str(content_item)
                )
            raw = "".join(texts)
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return raw

        if result.get("isError"):
            return {
                "outcome": "error",
                "message": f"Tool '{tool_name}' returned an error",
            }
        return {"outcome": "success", "result": str(result)}

    # ── Synchronous wrappers (for LangGraph nodes) ───────────────────────

    def call_tool_sync(self, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
        """Synchronous wrapper around ``call_tool()``."""
        return asyncio.run(self.call_tool(tool_name, arguments))

    def get_incident(self, incident_id: int) -> dict[str, Any]:
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
        args: dict[str, Any] = {}
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

    def get_product(self, product_id: int | None = None, sku: str | None = None, name: str | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {}
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

    def list_products(self, category: str | None = None, office: str | None = None) -> dict[str, Any]:
        args: dict[str, Any] = {}
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

    def reject_inventory_write(self, operation: str, **details: Any) -> dict[str, Any]:
        """Ask MCP to explicitly reject an inventory mutation attempt."""
        arguments = {"operation": operation, **details}
        result = self.call_tool_sync("reject_inventory_write", arguments)
        if isinstance(result, dict):
            return result
        return {"outcome": "error", "message": "Unexpected response format"}

    def create_incident(self, title: str, description: str, category: str, status: str, origin: str, branch: str) -> dict[str, Any]:
        result = self.call_tool_sync(
            "create_incident",
            {
                "title": title,
                "description": description,
                "category": category,
                "status": status,
                "origin": origin,
                "branch": branch,
            },
        )
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

    arguments: dict[str, Any] = {}
    if args.args_json:
        arguments = json.loads(args.args_json)

    # Parse key=value positional arguments for convenience
    for arg in sys.argv:
        if "=" in arg and not arg.startswith("--"):
            k, v = arg.split("=", 1)
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
