"""
Case-insensitive container-name matching — resolution, ambiguity, canonicalization.

Covers BOTH handlers, because they do the same job with different internal structure
and an earlier revision of this fix was built for edit_board's shape and silently did
not touch start_prioritization_flow's. Every test here drives the real resolver.

Three properties are under test, and they are coupled — see the invariant block in
board_utils.apply_priorities:

  1. RESOLUTION      names match case- and whitespace-insensitively
  2. THE >1 RULE     more than one eligible match -> error, never first-match-wins
  3. CANONICAL-FWD   the resolved container's STORED name reaches apply_priorities

(3) is only sound because of (2): a stored name is a unique handle only when exactly
one container can match. Relax (2) and (3) silently starts fanning out again.
"""

import copy

import pytest

from mcp_server.clarity.tools import edit_board as eb
from mcp_server.clarity.tools import start_prioritization_flow as spf
from mcp_server.clarity.tools.board_utils import (
    PriorityInput,
    apply_priorities,
    normalize_name,
)


# ============================================================================
# Fixtures
# ============================================================================


def screenshot_board():
    """The reported case: stored 'LinkedIn content', referenced as 'LinkedIn Content'."""
    return [{
        "cluster_name": "Positioning and visibility",
        "thought_items": [],
        "subclusters": [
            {"subcluster_name": "LinkedIn content", "thought_items": ["post weekly"]}
        ],
    }]


def duplicate_subcluster_board():
    """Two subclusters with the IDENTICAL name under different parents. No case variance."""
    return [
        {"cluster_name": "A", "subclusters": [{"subcluster_name": "Tasks", "thought_items": ["x"]}]},
        {"cluster_name": "B", "subclusters": [{"subcluster_name": "Tasks", "thought_items": ["y"]}]},
    ]


def case_variant_cluster_board():
    return [{"cluster_name": "Foo"}, {"cluster_name": "foo"}]


def _subcluster_priority(board, stored_name="LinkedIn content"):
    for c in board:
        for s in c.get("subclusters", []):
            if s.get("subcluster_name") == stored_name:
                return s.get("priority")
    return "<<container missing>>"


def _spf_validate(board, priorities):
    """Drive the real spf validation path, including its canonicalization."""
    indexes = spf._find_all_names(board)
    return spf._validate_priorities(priorities, board, *indexes)


# ============================================================================
# The shared normalizer
# ============================================================================


@pytest.mark.parametrize("raw,expected", [
    ("LinkedIn Content", "linkedin content"),
    ("  LinkedIn content  ", "linkedin content"),
    ("LINKEDIN CONTENT", "linkedin content"),
    ("", ""),
    (None, ""),
])
def test_normalize_name_semantics(raw, expected):
    """
    Bug this catches: divergence from the semantics thought-item matching already used.

    Deliberately NOT casefold/NFKC — containers must not match more aggressively than
    items, or the inconsistency simply flips direction.
    """
    assert normalize_name(raw) == expected


# ============================================================================
# THE REPORTED CASE — both handlers
# ============================================================================


def test_screenshot_case_resolves_via_start_prioritization_flow():
    """
    THE reported bug, on the handler that actually raised it.

    Bug this catches: fixing only _find_container_by_name (:200/:206). That function is
    on the item-target parent path and is never called for container targets, so
    normalizing it leaves this error byte-identical. Measured before the fix.

    Asserts the POSITIVE outcome (priority present afterwards), not merely absence of an
    error — an assertion on "no error" alone passes against the silent no-op this
    increment's canonicalization exists to prevent.
    """
    board = screenshot_board()
    priorities = [PriorityInput(name="LinkedIn Content", rank="P1", reason="relief")]

    assert _spf_validate(board, priorities) is None

    # Requirement 3: canonicalized to the STORED name before apply_priorities sees it.
    assert priorities[0].name == "LinkedIn content"

    applied = apply_priorities(board, priorities)
    assert _subcluster_priority(applied) == {"rank": "P1", "reason": "relief"}


def test_screenshot_case_resolves_via_edit_board():
    """Same reported case through edit_board's set_priority. Same positive assertion."""
    updated, error = eb._op_set_priority(screenshot_board(), "LinkedIn Content", None, None, "P1")

    assert error is None
    assert _subcluster_priority(updated) == {"rank": "P1", "reason": None}


@pytest.mark.parametrize("reference", [
    "LinkedIn Content",
    "linkedin content",
    "LINKEDIN CONTENT",
    "  LinkedIn content  ",
])
def test_container_resolution_is_case_and_whitespace_insensitive(reference):
    updated, error = eb._op_set_priority(screenshot_board(), reference, None, None, "P2")
    assert error is None
    assert _subcluster_priority(updated) == {"rank": "P2", "reason": None}


# ============================================================================
# CANONICAL-NAME-FORWARD (Requirement 3) — the measured blocker, kept as a guard
# ============================================================================


def test_set_priority_hands_apply_priorities_the_stored_name_not_the_input():
    """
    Bug this catches — MEASURED, not hypothesised: normalize the resolvers but leave the
    raw caller string on PriorityInput, and apply_priorities (an exact matcher) misses.
    Result is error=None with NO priority set: a silent no-op, and strictly worse than
    the not-found error it replaces, because it reports success.

    Fails-before/passes-after by construction.
    """
    board = screenshot_board()
    updated, error = eb._op_set_priority(board, "LINKEDIN CONTENT", None, None, "P1")

    assert error is None, "resolution must succeed"
    assert _subcluster_priority(updated) is not None, (
        "priority silently not applied — a raw name reached apply_priorities"
    )


def test_item_priority_canonicalizes_its_parent_name():
    """
    Same failure mode on the item branch: apply_priorities keys items
    (parent_name, index), so a raw parent name misses just as a raw container name does.
    """
    board = screenshot_board()
    priorities = [PriorityInput(item_index=0, parent_name="LINKEDIN CONTENT", rank="P1", reason="w")]

    assert _spf_validate(board, priorities) is None
    assert priorities[0].parent_name == "LinkedIn content"

    applied = apply_priorities(board, priorities)
    item = applied[0]["subclusters"][0]["thought_items"][0]
    assert isinstance(item, dict) and item.get("priority") == {"rank": "P1", "reason": "w"}


def test_find_thought_item_by_text_returns_the_stored_parent_name():
    """
    Bug this catches: search_container() used to be handed the CALLER's parent_name and
    echoed it back as resolved_parent, which _op_set_priority feeds straight into
    PriorityInput.parent_name — smuggling a raw name into apply_priorities.
    """
    index, resolved_parent, error = eb._find_thought_item_by_text(
        screenshot_board(), "POST WEEKLY", "linkedin CONTENT"
    )
    assert error is None
    assert index == 0
    assert resolved_parent == "LinkedIn content", "must be the stored name, not the input"


# ============================================================================
# THE >1 RULE — domain-scoped, fail-closed
# ============================================================================


def test_typed_operation_is_not_ambiguous_because_the_other_type_shares_a_name():
    """
    The candidate-domain rule. delete_cluster can only mean a cluster, so an unrelated
    subcluster named "x" must not block it.

    Bug this catches: collapsing the typed resolvers into one global cluster+subcluster
    resolver — which would falsely reject unambiguous typed operations. That would be a
    new bug shipped in the name of fixing this one.
    """
    board = [
        {"cluster_name": "X", "subclusters": []},
        {"cluster_name": "Other", "subclusters": [{"subcluster_name": "x", "thought_items": ["i"]}]},
    ]
    updated, error = eb._dispatch_operation(
        board, eb.SingleOperation(operation="delete_cluster", target_name="X")
    )
    assert error is None
    assert [c["cluster_name"] for c in updated] == ["Other"]


def test_both_types_operation_errors_when_a_name_spans_both_types():
    board = [{"cluster_name": "X", "subclusters": [{"subcluster_name": "x", "thought_items": ["i"]}]}]
    before = copy.deepcopy(board)

    updated, error = eb._dispatch_operation(
        board, eb.SingleOperation(operation="add_tag", target_name="X", tag="decide")
    )
    assert error is not None and "both a cluster and subcluster" in error
    assert updated is None
    assert board == before


def test_case_variant_duplicate_clusters_are_ambiguous_not_first_match():
    """
    Bug this catches: first-match-wins on delete. Deletion is unrecoverable, so guessing
    between "Foo" and "foo" would destroy data the user did not name.
    """
    board = case_variant_cluster_board()
    before = copy.deepcopy(board)

    updated, error = eb._dispatch_operation(
        board, eb.SingleOperation(operation="delete_cluster", target_name="FOO")
    )
    assert error is not None and "More than one cluster" in error
    assert updated is None, "zero mutation"
    assert board == before


def test_exact_duplicate_names_are_ambiguous_too(monkeypatch):
    """
    Q7 — DELIBERATE BEHAVIOUR CHANGE, and the one with no case variance involved.

    PREVIOUSLY: one PriorityInput naming "Tasks" set P1 on BOTH subclusters, silently,
    because apply_priorities matches board-wide and fans out to every match.
    NOW: ambiguity error, zero mutation.

    After normalization, exact duplicates and case variants are the same condition —
    one normalized key, several stored entries — so they get the same handling.
    """
    board = duplicate_subcluster_board()
    before = copy.deepcopy(board)

    error = _spf_validate(board, [PriorityInput(name="Tasks", rank="P1", reason="z")])

    assert error is not None and "More than one" in error
    assert board == before, "zero mutation"


def test_exact_duplicates_previously_fanned_out_to_every_match():
    """
    Pins the OLD behaviour this change replaces, so the reason for Q7 is not lost.

    apply_priorities is deliberately left an exact matcher and still fans out — that is
    why the >1 rule upstream is load-bearing rather than cosmetic. Calling it directly,
    bypassing validation, demonstrates what the rule now prevents.
    """
    board = duplicate_subcluster_board()
    applied = apply_priorities(board, [PriorityInput(name="Tasks", rank="P1", reason="z")])

    both = [c["subclusters"][0].get("priority") for c in applied]
    assert both == [{"rank": "P1", "reason": "z"}] * 2, (
        "apply_priorities fans out board-wide; the >1 rule is what stops this being reachable"
    )


def test_subcluster_ambiguity_is_scoped_to_the_named_parent():
    """
    Candidate-domain rule for subclusters: with a parent given, a same-named subcluster
    under a DIFFERENT parent neither resolves nor triggers ambiguity.
    """
    board = duplicate_subcluster_board()
    updated, error = eb._dispatch_operation(
        board,
        eb.SingleOperation(operation="delete_subcluster", target_name="tasks", parent_name="a"),
    )
    assert error is None
    assert updated[0]["subclusters"] == []
    assert len(updated[1]["subclusters"]) == 1, "the other parent's subcluster is untouched"


# ============================================================================
# RENAME — three distinct mechanisms
# ============================================================================


def test_rename_source_ambiguity_is_refused_with_zero_mutation():
    board = case_variant_cluster_board()
    before = copy.deepcopy(board)

    updated, error = eb._dispatch_operation(
        board, eb.SingleOperation(operation="rename_cluster", target_name="FOO", new_name="Bar")
    )
    assert error is not None and "More than one cluster" in error
    assert updated is None
    assert board == before


def test_rename_destination_collision_differing_only_by_case():
    board = [{"cluster_name": "Bar"}, {"cluster_name": "foo"}]
    before = copy.deepcopy(board)

    updated, error = eb._dispatch_operation(
        board, eb.SingleOperation(operation="rename_cluster", target_name="Bar", new_name="FOO")
    )
    assert error is not None and "already exists" in error
    assert updated is None
    assert board == before


def test_casing_only_self_rename_is_allowed():
    """
    A user fixing their own capitalisation must not collide with themselves.

    Bug this catches: replacing the `existing is not cluster` OBJECT-IDENTITY guard with
    a name comparison. Under normalization "foo" and "FOO" compare equal, so a
    name-based guard would reject this legitimate rename.
    """
    updated, error = eb._dispatch_operation(
        [{"cluster_name": "foo"}],
        eb.SingleOperation(operation="rename_cluster", target_name="foo", new_name="FOO"),
    )
    assert error is None
    assert updated == [{"cluster_name": "FOO"}]


def test_casing_only_self_rename_is_allowed_for_subclusters():
    board = [{"cluster_name": "P", "subclusters": [{"subcluster_name": "tasks", "thought_items": ["i"]}]}]
    updated, error = eb._dispatch_operation(
        board,
        eb.SingleOperation(
            operation="rename_subcluster", target_name="tasks", parent_name="p", new_name="Tasks"
        ),
    )
    assert error is None
    assert updated[0]["subclusters"][0]["subcluster_name"] == "Tasks"


# ============================================================================
# Q5 — the parent+child guard, which fails OPEN if normalization is partial
# ============================================================================


def test_parent_child_conflict_still_caught_under_case_variant_input():
    """
    Q5 — THE FAIL-OPEN SITE. Every other failure here fails closed (error, no mutation);
    this one, done wrong, produces no error at all and lets the board into a state the
    guard exists to forbid.

    It is correct only while prioritized_clusters, prioritized_subclusters and
    subcluster_to_parent all hold STORED names. Reintroduce a raw caller string into any
    one of them and this conflict goes undetected.
    """
    board = screenshot_board()
    before = copy.deepcopy(board)

    error = _spf_validate(board, [
        PriorityInput(name="POSITIONING AND VISIBILITY", rank="P1", reason="a"),
        PriorityInput(name="linkedin content", rank="P2", reason="b"),
    ])

    assert error == spf.ERROR_PARENT_AND_CHILD, "guard failed OPEN under case variance"
    assert board == before


def test_parent_child_conflict_still_caught_with_exact_names():
    """Control: the guard's original behaviour is unchanged for byte-exact names."""
    board = screenshot_board()
    error = _spf_validate(board, [
        PriorityInput(name="Positioning and visibility", rank="P1", reason="a"),
        PriorityInput(name="LinkedIn content", rank="P2", reason="b"),
    ])
    assert error == spf.ERROR_PARENT_AND_CHILD


# ============================================================================
# Q3 — ambiguity extension to set/clear_priority (deliberate behaviour change)
# ============================================================================


@pytest.mark.parametrize("operation", ["set_priority", "clear_priority"])
def test_priority_ops_by_target_name_now_reject_cross_type_ambiguity(operation):
    """
    Q3 — DELIBERATE BEHAVIOUR CHANGE. Previously _find_container checked clusters first,
    so an ambiguous name silently resolved to the cluster and the operation SUCCEEDED.

    Both set and clear are covered, deliberately: an asymmetry where set errors and
    clear silently picks would itself become a bug report.
    """
    board = [{"cluster_name": "X", "subclusters": [{"subcluster_name": "x", "thought_items": ["i"]}]}]
    before = copy.deepcopy(board)

    kwargs = {"operation": operation, "target_name": "X"}
    if operation == "set_priority":
        kwargs["rank"] = "P1"

    updated, error = eb._dispatch_operation(board, eb.SingleOperation(**kwargs))

    assert error is not None and "both a cluster and subcluster" in error
    assert updated is None
    assert board == before


# ============================================================================
# Zero-mutation / no-persist
# ============================================================================


@pytest.mark.parametrize("operation,kwargs", [
    ("delete_cluster", {"target_name": "FOO"}),
    ("rename_cluster", {"target_name": "FOO", "new_name": "Zed"}),
    ("add_tag", {"target_name": "FOO", "tag": "decide"}),
    ("set_priority", {"target_name": "FOO", "rank": "P1"}),
])
def test_ambiguous_target_never_mutates_the_board(operation, kwargs):
    """
    The rule's purpose is data integrity, so assert integrity — not merely that an error
    string came back. A handler could return an error AFTER mutating its working copy.
    """
    board = case_variant_cluster_board()
    before = copy.deepcopy(board)

    updated, error = eb._dispatch_operation(
        board, eb.SingleOperation(operation=operation, **kwargs)
    )

    assert error is not None
    assert updated is None, "None is what prevents the caller persisting a partial board"
    assert board == before


def test_ambiguity_surfaces_as_an_error_not_an_unhandled_exception():
    """
    The resolvers raise _AmbiguousContainerName rather than returning an error slot, so
    that no call site can forget to check it. This pins the boundary that converts it
    back into an ordinary (None, error) result — without it, ambiguity would surface as
    a 500 rather than a message the user can act on.
    """
    updated, error = eb._dispatch_operation(
        case_variant_cluster_board(),
        eb.SingleOperation(operation="delete_cluster", target_name="foo"),
    )
    assert isinstance(error, str) and error
    assert updated is None


def test_resolver_raises_when_called_outside_the_dispatch_boundary():
    """Complements the test above: the raise is real, not decorative."""
    with pytest.raises(eb._AmbiguousContainerName):
        eb._find_cluster(case_variant_cluster_board(), "FOO")


# ============================================================================
# HANDLER-LEVEL end-to-end — the screenshot's actual path
# ============================================================================
#
# Everything above drives resolvers and _op_* functions directly. That is where the
# logic lives, but it is NOT the level at which the reported bug reached a user: they
# called the TOOL, and the tool returned "Cluster or subcluster not found".
#
# These two tests close that gap. They drive the public `handle` with a case-variant
# name and assert BOTH halves of the outcome that matters:
#   - the priority is present in the returned board  (it resolved)
#   - persist_cluster was actually awaited            (it was written, not just computed)
#
# Asserting the returned board alone would pass even if persistence were skipped, and a
# priority that is never persisted is invisible the moment the board reloads — the same
# "looks fine, changed nothing" class as the canonical-name no-op.


@pytest.mark.asyncio
async def test_handler_screenshot_case_sets_and_persists_via_start_prioritization_flow():
    """
    THE reported bug at the level it was reported: the tool call itself.

    Bug this catches: any regression anywhere along handle -> _find_all_names ->
    _validate_priorities (canonicalization) -> _apply_priorities -> persist. The unit
    tests above pin each link; this pins the chain, which is what the user experiences.
    """
    from unittest.mock import AsyncMock, patch

    board = screenshot_board()

    with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster",
               new_callable=AsyncMock) as mock_get, \
         patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster",
               new_callable=AsyncMock) as mock_persist:
        mock_get.return_value = {"cluster_data": {"clusters": board}}
        mock_persist.return_value = "cluster-id-1"

        result = await spf.handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "user_prioritization_criterion_verbatim": "relief",
                "user_priorities_verbatim": "LinkedIn Content is my P1",
                # Capital C — the board stores "LinkedIn content".
                "priorities": [{"name": "LinkedIn Content", "rank": "P1", "reason": "relief"}],
            },
        )

    assert not result.isError, f"tool returned an error: {result.content}"

    persisted = result.structuredContent["clusters"]
    assert _subcluster_priority(persisted) == {"rank": "P1", "reason": "relief"}, (
        "resolved but the priority never landed — a silent no-op"
    )
    assert mock_persist.await_count == 1, "priority computed but never written"


@pytest.mark.asyncio
async def test_handler_ambiguous_name_returns_error_and_does_not_persist():
    """
    Fail-closed at the handler level: an ambiguous target must produce a tool error and
    write NOTHING.

    Bug this catches: an ambiguity that is detected but still reaches persist — the
    board would be written in a state the >1 rule exists to refuse. Asserting the error
    string alone would not catch that; only await_count == 0 does.
    """
    from unittest.mock import AsyncMock, patch

    board = duplicate_subcluster_board()

    with patch("mcp_server.clarity.tools.start_prioritization_flow.get_cluster",
               new_callable=AsyncMock) as mock_get, \
         patch("mcp_server.clarity.tools.start_prioritization_flow.persist_cluster",
               new_callable=AsyncMock) as mock_persist:
        mock_get.return_value = {"cluster_data": {"clusters": board}}

        result = await spf.handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "user_prioritization_criterion_verbatim": "relief",
                "user_priorities_verbatim": "Tasks is my P1",
                "priorities": [{"name": "Tasks", "rank": "P1", "reason": "relief"}],
            },
        )

    assert result.isError
    assert mock_persist.await_count == 0, "ambiguous target was persisted anyway"


@pytest.mark.asyncio
async def test_handler_screenshot_case_sets_and_persists_via_edit_board():
    """Same end-to-end assertion through edit_board's public handler."""
    from unittest.mock import AsyncMock, patch

    board = screenshot_board()

    with patch("mcp_server.clarity.tools.edit_board.get_cluster",
               new_callable=AsyncMock) as mock_get, \
         patch("mcp_server.clarity.tools.edit_board.persist_cluster",
               new_callable=AsyncMock) as mock_persist:
        mock_get.return_value = {"cluster_data": {"clusters": board}}
        mock_persist.return_value = "cluster-id-1"

        result = await eb.handle(
            user_id="test-user",
            correlation_id="test-corr",
            arguments={
                "operation": "set_priority",
                "target_name": "LinkedIn Content",   # capital C
                "rank": "P1",
            },
        )

    assert not result.isError, f"tool returned an error: {result.content}"
    assert _subcluster_priority(result.structuredContent["clusters"]) is not None
    assert mock_persist.await_count == 1, "priority computed but never written"


# ============================================================================
# ITEM-TARGET PARENT RESOLUTION — the >1 rule applies here too
# ============================================================================
#
# Found by adversarial review, not by the tests above, and the tests above could not
# have found it: every one of them targets a CONTAINER. The item-target path resolves
# its parent through a different function, and that function normalized without
# applying the >1 rule — so the fix reintroduced first-match-wins one level down.


def _duplicate_parent_board():
    """Same subcluster name under two different parents — no case variance needed."""
    return [
        {"cluster_name": "A", "subclusters": [{"subcluster_name": "Tasks", "thought_items": ["a0"]}]},
        {"cluster_name": "B", "subclusters": [{"subcluster_name": "Tasks", "thought_items": ["b0"]}]},
    ]


def _prioritized_item_count(board):
    return sum(
        1
        for c in board
        for s in c.get("subclusters", [])
        for i in s.get("thought_items", [])
        if isinstance(i, dict) and i.get("priority")
    )


@pytest.mark.parametrize("parent_reference", ["Tasks", "TASKS", "  tasks  "])
def test_item_target_duplicate_parent_is_ambiguous_not_first_match(parent_reference):
    """
    Bug this catches — REPRODUCED before the fix: one item priority landing on items in
    TWO containers.

    apply_priorities keys items (parent_name, index) and matches board-wide, so once a
    duplicated parent name resolves at all, the write fans out. The container-target
    path was protected by the >1 rule; this path was not.

    The case-variant reference is the worse half: before normalization "TASKS" errored
    with "Parent not found", so the fix turned a hard error into a silent double write.
    """
    board = _duplicate_parent_board()
    before = copy.deepcopy(board)
    priorities = [PriorityInput(item_index=0, parent_name=parent_reference, rank="P1", reason="r")]

    error = _spf_validate(board, priorities)

    assert error is not None and "More than one" in error
    assert board == before, "zero mutation"


def test_item_target_unique_parent_still_resolves_case_insensitively():
    """
    Control for the test above: the >1 rule must not break the feature it guards.
    A case-variant parent that is UNAMBIGUOUS still resolves, canonicalizes, and
    applies to exactly ONE container.
    """
    board = [
        {"cluster_name": "A", "subclusters": [{"subcluster_name": "Tasks", "thought_items": ["a0"]}]},
        {"cluster_name": "B", "subclusters": [{"subcluster_name": "Other", "thought_items": ["b0"]}]},
    ]
    priorities = [PriorityInput(item_index=0, parent_name="TASKS", rank="P1", reason="r")]

    assert _spf_validate(board, priorities) is None
    assert priorities[0].parent_name == "Tasks", "canonicalized to the stored name"

    applied = apply_priorities(board, priorities)
    assert _prioritized_item_count(applied) == 1, "fan-out: priority hit more than one container"


def test_find_container_by_name_enforces_the_rule_itself():
    """
    The >1 rule lives in the resolver, not the caller, so a future second caller
    inherits it. Pins that placement — a refactor moving the check up into
    _validate_priorities would leave this passing only by accident.
    """
    container, container_type, error = spf._find_container_by_name(
        _duplicate_parent_board(), "tasks"
    )
    assert container is None and container_type == ""
    assert error is not None and "More than one" in error
