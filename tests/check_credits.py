"""Check the OpenRouter API key's credit balance + rate limits.

Usage:
    python tests/check_credits.py

Reads the key from .env (or env var OPENROUTER_API_KEY).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tiny .env loader — keeps zero deps.
ENV_FILE = ROOT / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def _get(url: str, key: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "dfds-secure-agent-hackathon/0.1",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main() -> int:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not key or key.startswith("sk-or-v1-REPLACE"):
        print("OPENROUTER_API_KEY missing in .env / environment", file=sys.stderr)
        return 1

    masked = f"{key[:12]}…{key[-4:]}"
    print(f"key: {masked}")
    print()

    # 1. Key info — usage + limit + rate limit
    try:
        info = _get("https://openrouter.ai/api/v1/auth/key", key).get("data", {})
    except Exception as e:
        print(f"failed to fetch /auth/key: {e}", file=sys.stderr)
        return 2

    label = info.get("label") or "(no label)"
    usage = info.get("usage")  # USD spent
    limit = info.get("limit")  # USD cap, or None for unlimited
    free_tier = info.get("is_free_tier")
    rate_limit = info.get("rate_limit") or {}

    print(f"label         : {label}")
    print(f"is_free_tier  : {free_tier}")
    print(f"usage so far  : ${usage:.4f}" if isinstance(usage, (int, float)) else f"usage so far  : {usage}")
    if limit is None:
        print("limit         : (no cap)")
    else:
        remaining = max(limit - (usage or 0), 0)
        print(f"limit         : ${limit:.2f}")
        print(f"remaining     : ${remaining:.4f}  ({100*remaining/limit:.1f}% left)" if limit else "")
    if rate_limit:
        print(f"rate limit    : {rate_limit.get('requests')} req per {rate_limit.get('interval')}")

    # 2. Credits endpoint (newer; gives total_credits / total_usage)
    try:
        credits = _get("https://openrouter.ai/api/v1/credits", key).get("data", {})
    except Exception:
        credits = {}
    if credits:
        tc = credits.get("total_credits")
        tu = credits.get("total_usage")
        print()
        print("(/api/v1/credits)")
        if isinstance(tc, (int, float)):
            print(f"total credits : ${tc:.4f}")
        if isinstance(tu, (int, float)):
            print(f"total usage   : ${tu:.4f}")
        if isinstance(tc, (int, float)) and isinstance(tu, (int, float)):
            print(f"net remaining : ${tc - tu:.4f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
