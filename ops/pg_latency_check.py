#!/usr/bin/env python3
"""
Production Latency Verification for Priority Guardian.

One-shot diagnostic script to verify latency thresholds before OpenAI store submission.
Run against live Render services to catch cold-start issues and sluggish endpoints.

Usage:
    python ops/pg_latency_check.py

Thresholds:
    <300ms   - good
    300-500ms - acceptable
    500-1000ms - sluggish
    >1000ms  - timeout risk
"""

import time

import httpx

# Service URLs
BACKEND_URL = "https://priorities-guard-sdkapp-suite.onrender.com"
MCP_URL = "https://pg.priority-guard.com"

# Timeout for all requests
TIMEOUT_S = 15.0

# Threshold definitions (ms)
THRESHOLDS = [
    (300, "good", "✓"),
    (500, "acceptable", "~"),
    (1000, "sluggish", "!"),
    (float("inf"), "TIMEOUT RISK", "✗"),
]


def classify_latency(ms: float) -> tuple[str, str]:
    """Return (label, icon) for a given latency in ms."""
    for threshold, label, icon in THRESHOLDS:
        if ms < threshold:
            return label, icon
    return "TIMEOUT RISK", "✗"


def parse_sse_tool_count(response_text: str) -> int | None:
    """
    Parse SSE-framed response to extract tool count.

    Looks for data: lines containing JSON with tools array.
    Returns tool count or None if not found.
    """
    import json

    for line in response_text.split("\n"):
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                data = json.loads(data_str)
                # tools/list response has result.tools array
                if "result" in data and "tools" in data["result"]:
                    return len(data["result"]["tools"])
            except json.JSONDecodeError:
                continue
    return None


def measure_endpoint(
    client: httpx.Client,
    method: str,
    url: str,
    label: str,
    json_body: dict | None = None,
    extra_headers: dict | None = None,
) -> dict:
    """
    Measure latency for a single endpoint.

    Returns dict with: method, label, url, elapsed_ms, status, threshold_label, icon, error
    """
    headers = extra_headers or {}

    start = time.perf_counter()
    try:
        if method == "GET":
            response = client.get(url, headers=headers)
        elif method == "HEAD":
            response = client.head(url, headers=headers)
        elif method == "POST":
            response = client.post(url, json=json_body, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        elapsed_ms = (time.perf_counter() - start) * 1000
        threshold_label, icon = classify_latency(elapsed_ms)

        result = {
            "method": method,
            "label": label,
            "url": url,
            "elapsed_ms": elapsed_ms,
            "status": response.status_code,
            "threshold_label": threshold_label,
            "icon": icon,
            "error": None,
        }

        # For POST /mcp, extract tool count from SSE response
        if method == "POST" and "/mcp" in url:
            tool_count = parse_sse_tool_count(response.text)
            if tool_count is not None:
                result["tool_count"] = tool_count

        return result

    except httpx.TimeoutException:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "method": method,
            "label": label,
            "url": url,
            "elapsed_ms": elapsed_ms,
            "status": None,
            "threshold_label": "TIMEOUT",
            "icon": "✗",
            "error": "Request timed out",
        }
    except httpx.RequestError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "method": method,
            "label": label,
            "url": url,
            "elapsed_ms": elapsed_ms,
            "status": None,
            "threshold_label": "ERROR",
            "icon": "✗",
            "error": str(e),
        }


def print_result(result: dict) -> None:
    """Print a single result line."""
    icon = result["icon"]
    method = result["method"].ljust(4)
    label = result["label"].ljust(35)
    elapsed = f"{result['elapsed_ms']:7.0f}ms"

    if result["error"]:
        status = f"ERR: {result['error'][:30]}"
    else:
        status = f"{result['status']}"

    threshold = result["threshold_label"]

    extra = ""
    if "tool_count" in result:
        extra = f" ({result['tool_count']} tools)"

    print(f"{icon} {method} {label} {elapsed}  {status:>5}  {threshold}{extra}")


def main():
    print("=" * 80)
    print("Priority Guardian Production Latency Check")
    print("=" * 80)
    print(f"Backend: {BACKEND_URL}")
    print(f"MCP:     {MCP_URL}")
    print(f"Timeout: {TIMEOUT_S}s")
    print("-" * 80)

    # Define endpoints to test
    endpoints = [
        # Backend endpoints
        ("GET", f"{BACKEND_URL}/", "Backend root", None, None),
        ("GET", f"{BACKEND_URL}/api/priority-guardian/health", "Backend health", None, None),
        ("GET", f"{BACKEND_URL}/.well-known/openid-configuration", "Backend OIDC discovery", None, None),
        ("GET", f"{BACKEND_URL}/oauth/pg/jwks", "Backend JWKS", None, None),
        # MCP endpoints
        ("GET", f"{MCP_URL}/", "MCP root", None, None),
        ("GET", f"{MCP_URL}/health", "MCP health", None, None),
        ("HEAD", f"{MCP_URL}/mcp", "MCP reachability probe", None, None),
        ("GET", f"{MCP_URL}/.well-known/oauth-protected-resource", "MCP protected resource", None, None),
        (
            "POST",
            f"{MCP_URL}/mcp",
            "MCP tools/list (SSE)",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {"Accept": "application/json, text/event-stream"},
        ),
    ]

    results = []

    with httpx.Client(timeout=TIMEOUT_S) as client:
        for method, url, label, json_body, extra_headers in endpoints:
            result = measure_endpoint(client, method, url, label, json_body, extra_headers)
            results.append(result)
            print_result(result)

    # Summary
    print("-" * 80)

    good = sum(1 for r in results if r["threshold_label"] == "good")
    acceptable = sum(1 for r in results if r["threshold_label"] == "acceptable")
    sluggish = sum(1 for r in results if r["threshold_label"] == "sluggish")
    timeout_risk = sum(1 for r in results if r["threshold_label"] in ("TIMEOUT RISK", "TIMEOUT", "ERROR"))

    total = len(results)
    avg_ms = sum(r["elapsed_ms"] for r in results) / total if total else 0
    max_ms = max(r["elapsed_ms"] for r in results) if results else 0

    print(f"Summary: {good} good, {acceptable} acceptable, {sluggish} sluggish, {timeout_risk} at risk")
    print(f"Average: {avg_ms:.0f}ms | Max: {max_ms:.0f}ms")

    if timeout_risk > 0:
        print("\n⚠️  Some endpoints are at timeout risk. Investigate before submission.")
    elif sluggish > 0:
        print("\n⚠️  Some endpoints are sluggish. Consider optimizing.")
    else:
        print("\n✓ All endpoints within acceptable latency thresholds.")

    print("=" * 80)


if __name__ == "__main__":
    main()
