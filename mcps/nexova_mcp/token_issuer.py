"""
Token issuer — utility to mint JWT access tokens for MCP Server testing.

Usage:
    python -m mcps.nexova_mcp.token_issuer --sub alice --scopes "incidents:read incidents:write"

The token is signed with the same ``JWT_SECRET_KEY`` from ``.env`` so that
``mcps/nexova_mcp/auth.py``'s ``introspect_token()`` accepts it.

Output:
    Access token (JWT) printed to stdout.
    Expiration: 1 hour by default (override with --exp-hours).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

# ── Ensure .env is loaded ───────────────────────────────────────────────
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    print("ERROR: JWT_SECRET_KEY not found in .env", file=sys.stderr)
    sys.exit(1)


def mint_token(
    sub: str,
    scopes: list[str],
    exp_hours: int = 1,
    purpose: str = "access",
) -> str:
    """Create a signed JWT access token.

    Parameters
    ----------
    sub : str
        Subject (user or client ID).
    scopes : list[str]
        OAuth 2.0 scope list (e.g. ``["incidents:read", "inventory:read"]``).
    exp_hours : int
        Token lifetime in hours (default 1).
    purpose : str
        Token purpose (default "access").  The MCP server rejects tokens
        with purpose != "access".

    Returns
    -------
    str
        Encoded JWT string.
    """
    from jose import jwt

    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": sub,
        "scope": " ".join(scopes),
        "purpose": purpose,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=exp_hours)).timestamp()),
        "iss": "http://localhost:8010",
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm="HS256")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Mint a JWT access token for the Nexova MCP Server.",
    )
    parser.add_argument(
        "--sub",
        default="test-client",
        help="Subject (user / client ID). Default: test-client",
    )
    parser.add_argument(
        "--scopes",
        default="incidents:read inventory:read",
        help=(
            "Space-separated scope list. "
            "Available: incidents:read, incidents:write, inventory:read. "
            "Default: 'incidents:read inventory:read'"
        ),
    )
    parser.add_argument(
        "--exp-hours",
        type=int,
        default=1,
        help="Token lifetime in hours. Default: 1",
    )
    parser.add_argument(
        "--purpose",
        default="access",
        help="Token purpose. Default: access",
    )
    args = parser.parse_args()

    token = mint_token(
        sub=args.sub,
        scopes=args.scopes.split(),
        exp_hours=args.exp_hours,
        purpose=args.purpose,
    )
    print(token)


if __name__ == "__main__":
    main()