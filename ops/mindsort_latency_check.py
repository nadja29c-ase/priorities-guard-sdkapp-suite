#!/usr/bin/env python3
"""
Production Latency Verification for MindSort AI.

One-shot diagnostic script to verify latency thresholds before OpenAI store submission.
Run against live Render services to catch cold-start issues and sluggish endpoints.

Usage:
    # Infrastructure only (no auth required):
    python ops/mindsort_latency_check.py

    # Full test including authenticated tool calls:
    MINDSORT_JWT=<your_token> python ops/mindsort_latency_check.py

Thresholds:
    <300ms   - good
    300-500ms - acceptable
    500-1000ms - sluggish
    >1000ms  - timeout risk

Tool call thresholds (DB-bound, higher allowance):
    <2000ms  - good
    2000-4000ms - acceptable
    4000-8000ms - sluggish (approaching OpenAI 8s timeout)
    >8000ms  - TIMEOUT RISK (will fail in ChatGPT)

The 8s limit comes from ChatGPT's server-side timeout for tool calls.
Cold starts on Render Hobby tier take 30-60s — ensure service is warm before submission.
"""

import json
import os
import sys
import time

import httpx

# ============================================================================
# Service URLs
# ============================================================================

BACKEND_URL = "https://priorities-guard-sdkapp-suite.onrender.com"
MINDSORT_MCP_URL = "https://priorities-guard-clarity-mcp.onrender.com"

# ============================================================================
# Auth token (optional — enables tool call tests)
# ============================================================================

JWT_TOKEN = os.environ.get("MINDSORT_JWT", "")

# ============================================================================
# Timeouts
# ============================================================================

TIMEOUT_S = 15.0          # Infrastructure endpoints
TOOL_TIMEOUT_S = 30.0     # Tool calls (allow for cold start measurement)

# ============================================================================
# Threshold definitions
# ============================================================================

INFRA_THRESHOLDS = [
    (300, "good", "✓"),
    (500, "acceptable", "~"),
    (1000, "sluggish", "!"),
    (float("inf"), "TIMEOUT RISK", "✗"),
]

TOOL_THRESHOLDS = [
    (2000, "good", "✓"),
    (4000, "acceptable", "~"),
    (8000, "sluggish — approaching timeout", "!"),
    (float("inf"), "TIMEOUT RISK — will fail in ChatGPT", "✗"),
]


def classify_latency(ms: float, tool_call: bool = False) -> tuple[str, str]:
    """Return (label, icon) for a given latency in ms."""
    thresholds = TOOL_THRESHOLDS if tool_call else INFRA_THRESHOLDS
    for threshold, label, icon in thresholds:
        if ms < threshold:
            return label, icon
    return ("TIMEOUT RISK — will fail in ChatGPT" if tool_call else "TIMEOUT RISK"), "✗"


def parse_sse_response(response_text: str) -> dict | None:
    """
    Parse SSE-framed MCP response body.

    Returns the first result/error object found, or None.
    """
    for line in response_text.split("\n"):
        if line.startswith("data:"):
            data_str = line[5:].strip()
            if not data_str:
                continue
            try:
                data = json.loads(data_str)
                if "result" in data or "error" in data:
                    return data
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
    tool_call: bool = False,
) -> dict:
    """
    Measure latency for a single endpoint.

    Returns result dict with timing and classification.
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
        threshold_label, icon = classify_latency(elapsed_ms, tool_call=tool_call)

        result = {
            "method": method,
            "label": label,
            "url": url,
            "elapsed_ms": elapsed_ms,
            "status": response.status_code,
            "threshold_label": threshold_label,
            "icon": icon,
            "error": None,
            "tool_call": tool_call,
        }

        # For MCP POST, parse SSE response for error details
        if method == "POST" and "/mcp" in url:
            parsed = parse_sse_response(response.text)
            if parsed:
                if "error" in parsed:
                    result["mcp_error"] = parsed["error"].get("message", "unknown error")
                elif "result" in parsed:
                    res = parsed["result"]
                    # Check for tool-level isError
                    if res.get("isError"):
                        content = res.get("content", [{}])
                        msg = content[0].get("text", "tool error") if content else "tool error"
                        result["mcp_error"] = f"tool error: {msg[:60]}"
                    else:
                        # Count tools for tools/list
                        if "tools" in res:
                            result["tool_count"] = len(res["tools"])

        return result

    except httpx.TimeoutException:
        elapsed_ms = (time.perf_counter() - start) * 1000
        label_suffix = " — will fail in ChatGPT" if tool_call else ""
        return {
            "method": method,
            "label": label,
            "url": url,
            "elapsed_ms": elapsed_ms,
            "status": None,
            "threshold_label": f"TIMEOUT{label_suffix}",
            "icon": "✗",
            "error": f"Request timed out after {TOOL_TIMEOUT_S if tool_call else TIMEOUT_S}s",
            "tool_call": tool_call,
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
            "tool_call": tool_call,
        }


def print_result(result: dict) -> None:
    """Print a single result line."""
    icon = result["icon"]
    method = result["method"].ljust(4)
    label = result["label"].ljust(45)
    elapsed = f"{result['elapsed_ms']:7.0f}ms"

    if result["error"]:
        status = f"ERR"
        detail = f"  {result['error'][:50]}"
    elif result.get("mcp_error"):
        status = f"{result['status']}"
        detail = f"  ⚠ {result['mcp_error'][:50]}"
    else:
        status = f"{result['status']}"
        detail = ""

    threshold = result["threshold_label"]

    extra = ""
    if "tool_count" in result:
        extra = f" ({result['tool_count']} tools)"

    print(f"{icon} {method} {label} {elapsed}  {status:>5}  {threshold}{extra}{detail}")


def build_tool_call_body(tool_name: str, arguments: dict) -> dict:
    """Build a JSON-RPC 2.0 tool call body."""
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }


def main():
    print("=" * 80)
    print("MindSort AI Production Latency Check")
    print("=" * 80)
    print(f"Backend:      {BACKEND_URL}")
    print(f"MindSort MCP: {MINDSORT_MCP_URL}")
    print(f"Timeout:      {TIMEOUT_S}s (infra) / {TOOL_TIMEOUT_S}s (tool calls)")

    if JWT_TOKEN:
        print("Auth:         JWT token provided — tool call tests ENABLED")
    else:
        print("Auth:         No JWT token — tool call tests SKIPPED")
        print("              Set MINDSORT_JWT=<token> to enable tool call latency tests")

    print("-" * 80)

    # ============================================================
    # SECTION 1: Infrastructure endpoints (no auth required)
    # ============================================================

    print("\n[Infrastructure Endpoints]")

    infra_endpoints = [
        # Backend
        ("GET", f"{BACKEND_URL}/", "Backend root", None, None),
        ("GET", f"{BACKEND_URL}/api/priority-guardian/health", "Backend health", None, None),
        ("GET", f"{BACKEND_URL}/.well-known/openid-configuration", "Backend OIDC discovery", None, None),
        ("GET", f"{BACKEND_URL}/oauth/mindsort/jwks", "Backend JWKS (MindSort)", None, None),
        # MindSort MCP
        ("GET", f"{MINDSORT_MCP_URL}/", "MindSort MCP root", None, None),
        ("GET", f"{MINDSORT_MCP_URL}/health", "MindSort MCP health", None, None),
        ("HEAD", f"{MINDSORT_MCP_URL}/mcp", "MindSort MCP reachability probe", None, None),
        ("GET", f"{MINDSORT_MCP_URL}/.well-known/oauth-protected-resource", "Protected resource metadata", None, None),
        ("GET", f"{MINDSORT_MCP_URL}/.well-known/oauth-authorization-server", "OAuth authorization server", None, None),
        (
            "POST",
            f"{MINDSORT_MCP_URL}/mcp",
            "MCP tools/list (discovery)",
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            {"Accept": "application/json, text/event-stream"},
        ),
    ]

    infra_results = []
    with httpx.Client(timeout=TIMEOUT_S) as client:
        for method, url, label, json_body, extra_headers in infra_endpoints:
            result = measure_endpoint(client, method, url, label, json_body, extra_headers)
            infra_results.append(result)
            print_result(result)

    # ============================================================
    # SECTION 2: Authenticated tool calls (JWT required)
    # ============================================================

    tool_results = []

    if JWT_TOKEN:
        print("\n[Tool Call Latency — Cold Start & Warm]")
        print("  Each tool called TWICE: first call measures cold-start risk,")
        print("  second call measures warm latency (what users experience).")
        print()

        auth_headers = {
            "Authorization": f"Bearer {JWT_TOKEN}",
            "Accept": "application/json, text/event-stream",
        }

        # Tools ordered by latency risk (DB-read tools first, then write tools)
        # Arguments are minimal/safe — read tools use no args, write tools are skipped
        # to avoid mutating reviewer test account data.
        #
        # NOTE: organize_thoughts, edit_board, start_prioritization_flow, delete_my_data
        # are intentionally excluded — calling them would mutate the test account board.
        # Test those manually in ChatGPT with the reviewer account.
        read_tools = [
            ("load_saved_board", {}, "load_saved_board (DB read + widget)"),
            ("read_board_before_editing", {}, "read_board_before_editing (DB read, no widget)"),
        ]

        with httpx.Client(timeout=TOOL_TIMEOUT_S) as client:
            for tool_name, arguments, label in read_tools:
                body = build_tool_call_body(tool_name, arguments)

                # First call (cold start risk)
                result1 = measure_endpoint(
                    client,
                    "POST",
                    f"{MINDSORT_MCP_URL}/mcp",
                    f"{label} [call 1]",
                    body,
                    auth_headers,
                    tool_call=True,
                )
                tool_results.append(result1)
                print_result(result1)

                # Second call (warm)
                result2 = measure_endpoint(
                    client,
                    "POST",
                    f"{MINDSORT_MCP_URL}/mcp",
                    f"{label} [call 2 warm]",
                    body,
                    auth_headers,
                    tool_call=True,
                )
                tool_results.append(result2)
                print_result(result2)
                print()

        print("  Write tools (organize_thoughts, edit_board, start_prioritization_flow,")
        print("  delete_my_data) excluded from automated test — test manually in ChatGPT")
        print("  with reviewer account to avoid mutating test data.")

    # ============================================================
    # SUMMARY
    # ============================================================

    all_results = infra_results + tool_results

    print("\n" + "-" * 80)
    print("Summary")
    print("-" * 80)

    # Infrastructure summary
    infra_good = sum(1 for r in infra_results if r["threshold_label"] == "good")
    infra_acceptable = sum(1 for r in infra_results if r["threshold_label"] == "acceptable")
    infra_sluggish = sum(1 for r in infra_results if r["threshold_label"] == "sluggish")
    infra_risk = sum(1 for r in infra_results if r["threshold_label"] not in ("good", "acceptable", "sluggish"))

    print(f"Infrastructure ({len(infra_results)} endpoints):")
    print(f"  ✓ {infra_good} good  ~ {infra_acceptable} acceptable  ! {infra_sluggish} sluggish  ✗ {infra_risk} at risk")

    if infra_results:
        avg_infra = sum(r["elapsed_ms"] for r in infra_results) / len(infra_results)
        max_infra = max(r["elapsed_ms"] for r in infra_results)
        print(f"  Average: {avg_infra:.0f}ms | Max: {max_infra:.0f}ms")

    if tool_results:
        tool_good = sum(1 for r in tool_results if r["threshold_label"] == "good")
        tool_acceptable = sum(1 for r in tool_results if "acceptable" in r["threshold_label"])
        tool_sluggish = sum(1 for r in tool_results if "sluggish" in r["threshold_label"])
        tool_risk = sum(1 for r in tool_results if "TIMEOUT" in r["threshold_label"] or r["icon"] == "✗")

        print(f"\nTool calls ({len(tool_results)} calls):")
        print(f"  ✓ {tool_good} good  ~ {tool_acceptable} acceptable  ! {tool_sluggish} sluggish  ✗ {tool_risk} at risk")

        avg_tool = sum(r["elapsed_ms"] for r in tool_results) / len(tool_results)
        max_tool = max(r["elapsed_ms"] for r in tool_results)
        print(f"  Average: {avg_tool:.0f}ms | Max: {max_tool:.0f}ms")
        print(f"  ChatGPT timeout ceiling: 8000ms")
        if max_tool > 8000:
            print(f"  ✗ SUBMISSION BLOCKER: max tool latency ({max_tool:.0f}ms) exceeds ChatGPT 8s timeout")
        elif max_tool > 4000:
            print(f"  ! WARNING: max tool latency ({max_tool:.0f}ms) is sluggish — review cold start config")
        else:
            print(f"  ✓ All tool calls within safe threshold")

    # Overall verdict
    total_risk = sum(1 for r in all_results if r["icon"] == "✗")
    print()
    if total_risk > 0:
        print("⚠️  ISSUES FOUND — do not submit until resolved")
        print("   Common causes:")
        print("   - Render service on Free tier (spins down) → upgrade to Hobby")
        print("   - Backend cold start → check backend is Hobby tier too")
        print("   - DB connection pool exhausted → check Render logs")
    else:
        print("✓ All checks passed — latency thresholds met for submission")

    print("=" * 80)

    # Exit with non-zero if any critical failures
    if total_risk > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
