"""
Acceptance gate for the malformed-input guards on start_prioritization_flow.

This is the CI half of the gate. It does NOT mock away the round-trip the way the
sibling integration modules do: `get_cluster` / `persist_cluster` are backed by a
stateful in-memory store, so "the previously-stored P1 survived the malformed
call" is a real assertion about persisted state, not about a return value.

The defect being gated (production, 2026-08-18): a malformed invocation resolved
`priorities` to [], `apply_priorities([])` took the clear-all branch, and the
handler PERSISTED the erasure — a call meant to SET a priority silently ERASED
the board's priorities.

The live half of the gate (mocked-green != works-in-production) is the post-deploy
check against mindsort-mcp.priority-guard.com, recorded in the increment report.
"""

from unittest.mock import patch

import pytest

from mcp_server.clarity.tools.start_prioritization_flow import handle


CRITERION = "removing a blocker"


class InMemoryBoardStore:
    """Stateful stand-in for the persistence layer (one board, one user)."""

    def __init__(self):
        self.record = None
        self.persist_calls = 0

    async def get_cluster(self, user_id, correlation_id=None, **kwargs):
        return self.record

    async def persist_cluster(self, user_id, cluster_data, correlation_id=None, **kwargs):
        self.persist_calls += 1
        self.record = {"cluster_data": cluster_data}
        return "cluster-in-memory-1"

    def priority_of(self, cluster_name):
        """The persisted priority for a cluster, or None."""
        clusters = (self.record or {}).get("cluster_data", {}).get("clusters", [])
        for cluster in clusters:
            if cluster.get("cluster_name") == cluster_name:
                return cluster.get("priority")
        raise AssertionError(f"cluster {cluster_name!r} missing from persisted board")


@pytest.fixture
def store():
    s = InMemoryBoardStore()
    s.record = {
        "cluster_data": {
            "clusters": [
                {"cluster_name": "Client work", "thought_items": ["ship the deck"], "subclusters": []},
                {"cluster_name": "Admin", "thought_items": ["invoices"], "subclusters": []},
            ]
        }
    }
    with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster", new=s.get_cluster), \
         patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster", new=s.persist_cluster):
        yield s


async def _set_p1(store):
    """Step 1: a well-formed call that persists P1 on 'Client work'."""
    result = await handle(
        user_id="acceptance-user",
        correlation_id="acceptance-corr",
        arguments={
            "user_prioritization_criterion_verbatim": CRITERION,
            "user_priorities_verbatim": "the client work is my number one",
            "priorities": [{"name": "Client work", "rank": "P1", "reason": "blocker"}],
        },
    )
    assert result.isError is None or result.isError is False
    assert store.priority_of("Client work")["rank"] == "P1"
    return result


@pytest.mark.asyncio
async def test_production_malformed_shape_fails_closed_and_preserves_p1(store):
    """
    The EXACT malformed invocation class from the production incident:
    `priorities` absent, top-level `priority_1` / `priority_1_parent_cluster`.
    """
    await _set_p1(store)
    persists_before = store.persist_calls

    result = await handle(
        user_id="acceptance-user",
        correlation_id="acceptance-corr",
        arguments={
            "user_prioritization_criterion_verbatim": CRITERION,
            "user_priorities_verbatim": "admin is my number two",
            "priority_1": "Admin",
            "priority_1_parent_cluster": "Admin",
        },
    )

    # Fail closed, and say so machine-readably.
    assert result.isError is True
    assert result.structuredContent["error"] == "unknown_top_level_fields"
    assert result.structuredContent["state_modified"] is False

    # Nothing was written...
    assert store.persist_calls == persists_before
    # ...and the previously-stored P1 is intact.
    assert store.priority_of("Client work")["rank"] == "P1"
    assert store.priority_of("Admin") is None


@pytest.mark.asyncio
async def test_missing_priorities_key_preserves_p1(store):
    """Guard B against real persisted state."""
    await _set_p1(store)
    persists_before = store.persist_calls

    result = await handle(
        user_id="acceptance-user",
        correlation_id="acceptance-corr",
        arguments={
            "user_prioritization_criterion_verbatim": CRITERION,
            "user_priorities_verbatim": "admin is my number two",
        },
    )

    assert result.isError is True
    assert result.structuredContent["error"] == "missing_priorities"
    assert result.structuredContent["state_modified"] is False
    assert store.persist_calls == persists_before
    assert store.priority_of("Client work")["rank"] == "P1"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_value", ["Client work", {"name": "Admin", "rank": "P2"}])
async def test_non_list_priorities_preserves_p1(store, bad_value):
    """Guard C against real persisted state — string and object variants."""
    await _set_p1(store)
    persists_before = store.persist_calls

    result = await handle(
        user_id="acceptance-user",
        correlation_id="acceptance-corr",
        arguments={
            "user_prioritization_criterion_verbatim": CRITERION,
            "user_priorities_verbatim": "admin is my number two",
            "priorities": bad_value,
        },
    )

    assert result.isError is True
    assert result.structuredContent["error"] == "invalid_priorities_type"
    assert result.structuredContent["state_modified"] is False
    assert store.persist_calls == persists_before
    assert store.priority_of("Client work")["rank"] == "P1"


@pytest.mark.asyncio
async def test_explicit_empty_list_still_clears_and_persists(store):
    """
    No over-reach: `[]` is a present list, so it passes A/B/C and reaches the
    intended clear-all path — which DOES write.
    """
    await _set_p1(store)
    persists_before = store.persist_calls

    result = await handle(
        user_id="acceptance-user",
        correlation_id="acceptance-corr",
        arguments={
            "user_prioritization_criterion_verbatim": CRITERION,
            "user_priorities_verbatim": "clear them, I want to start over",
            "priorities": [],
        },
    )

    assert result.isError is None or result.isError is False
    assert store.persist_calls == persists_before + 1
    assert store.priority_of("Client work") is None


@pytest.mark.asyncio
async def test_cumulative_retry_after_rejection_restores_intent(store):
    """
    End-to-end shape of the self-correction the error is designed to produce:
    malformed call rejected, then the model reissues the FULL cumulative array
    and both priorities land. Guards against the rejection path leaving the user
    unable to complete what they were doing.
    """
    await _set_p1(store)

    rejected = await handle(
        user_id="acceptance-user",
        correlation_id="acceptance-corr",
        arguments={
            "user_prioritization_criterion_verbatim": CRITERION,
            "user_priorities_verbatim": "admin is my number two",
            "priority_2": "Admin",
        },
    )
    assert rejected.isError is True

    retried = await handle(
        user_id="acceptance-user",
        correlation_id="acceptance-corr",
        arguments={
            "user_prioritization_criterion_verbatim": CRITERION,
            "user_priorities_verbatim": "admin is my number two",
            "priorities": [
                {"name": "Client work", "rank": "P1", "reason": "blocker"},
                {"name": "Admin", "rank": "P2", "reason": "blocker"},
            ],
        },
    )

    assert retried.isError is None or retried.isError is False
    assert store.priority_of("Client work")["rank"] == "P1"
    assert store.priority_of("Admin")["rank"] == "P2"
