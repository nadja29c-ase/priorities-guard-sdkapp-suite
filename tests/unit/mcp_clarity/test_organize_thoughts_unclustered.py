"""
Unit tests for Unclustered min-2 validator exemption (inc_13).

Tests the fix for production bug where organize_thoughts failed with
"Invalid input format" when exactly one item landed in Unclustered.

Root cause: ClusterInput.validate_cluster enforced min-2 items globally,
but the repair loop creates one-item Unclustered clusters by design.
Fix: Exempt cluster_name == "Unclustered" from min-2 rule (exact match).

Test categories:
- Validator unit tests (ClusterInput directly)
- Repair path tests (handle() round-trip with mocked persistence)
- Log assertion tests (Change B)
"""

from unittest.mock import AsyncMock, patch, ANY
import pytest
from pydantic import ValidationError

from mcp_server.clarity.tools.organize_thoughts import ClusterInput, handle


# =============================================================================
# Validator Unit Tests
# =============================================================================


class TestUnclusteredMin2Exemption:
    """Tests for ClusterInput validator's Unclustered exemption."""

    def test_unclustered_with_one_item_passes_validation(self):
        """
        Model-supplied Unclustered with exactly 1 item passes validation.

        The exemption applies regardless of how the cluster arose — direct
        model submission or repair loop output.

        Bug that would still pass: None — this directly tests the exemption.
        """
        cluster = ClusterInput(
            cluster_name="Unclustered",
            thought_items=["single orphan item"],
            subclusters=[],
            tags=[],
        )
        assert cluster.cluster_name == "Unclustered"
        assert len(cluster.thought_items) == 1

    def test_ordinary_cluster_with_one_item_fails_validation(self):
        """
        Ordinary named cluster with 1 item still fails validation.

        The min-2 rule is not weakened globally — only Unclustered is exempt.

        Bug that would still pass: If exemption applied to all clusters,
        this test would fail (regression guard).
        """
        with pytest.raises(ValidationError) as exc_info:
            ClusterInput(
                cluster_name="Work",
                thought_items=["single item"],
                subclusters=[],
                tags=[],
            )
        assert "Minimum 2 required" in str(exc_info.value)

    def test_unclustered_case_sensitive_lowercase_fails(self):
        """
        Cluster named "unclustered" (lowercase) with 1 item fails validation.

        The exemption is exact, case-sensitive. Lowercase "unclustered" is
        treated as an ordinary cluster name.

        Bug that would still pass: Case-insensitive exemption.
        """
        with pytest.raises(ValidationError) as exc_info:
            ClusterInput(
                cluster_name="unclustered",
                thought_items=["single item"],
                subclusters=[],
                tags=[],
            )
        assert "Minimum 2 required" in str(exc_info.value)

    def test_unclustered_case_sensitive_uppercase_fails(self):
        """
        Cluster named "UNCLUSTERED" (uppercase) with 1 item fails validation.

        Bug that would still pass: Case-insensitive exemption.
        """
        with pytest.raises(ValidationError) as exc_info:
            ClusterInput(
                cluster_name="UNCLUSTERED",
                thought_items=["single item"],
                subclusters=[],
                tags=[],
            )
        assert "Minimum 2 required" in str(exc_info.value)

    def test_unclustered_with_two_items_passes(self):
        """
        Unclustered with 2+ items passes validation (baseline sanity check).

        Bug that would still pass: None — sanity check for normal path.
        """
        cluster = ClusterInput(
            cluster_name="Unclustered",
            thought_items=["item1", "item2"],
            subclusters=[],
            tags=[],
        )
        assert len(cluster.thought_items) == 2

    def test_ordinary_cluster_with_two_items_passes(self):
        """
        Ordinary cluster with 2+ items passes validation (baseline sanity check).

        Bug that would still pass: None — sanity check for normal path.
        """
        cluster = ClusterInput(
            cluster_name="Work",
            thought_items=["item1", "item2"],
            subclusters=[],
            tags=[],
        )
        assert len(cluster.thought_items) == 2


# =============================================================================
# Repair Path Tests (handle() round-trip)
# =============================================================================


class TestRepairPathWithUnclusteredExemption:
    """Tests for repair loop producing one-item Unclustered clusters."""

    @pytest.fixture
    def valid_provenance_args(self):
        """Common provenance fields for all handle() calls."""
        return {
            "user_thoughts_exhausted_verbatim": "that's it",
            "user_confirmed_no_more_thoughts": True,
            "thoughts_exhausted": True,
        }

    @pytest.mark.asyncio
    async def test_incident_payload_one_orphan_no_existing_unclustered(
        self, valid_provenance_args
    ):
        """
        THE INCIDENT: One single-item cluster among valid clusters.

        Repair produces one-item Unclustered → validation passes → success.

        Bug that would still pass: If validator was fixed but repair loop
        broke, this would fail (end-to-end guard).
        """
        with patch(
            "mcp_server.clarity.tools.organize_thoughts.persist_cluster",
            new_callable=AsyncMock,
        ) as mock_persist:
            mock_persist.return_value = "cluster-123"

            result = await handle(
                user_id="test",
                correlation_id="test",
                arguments={
                    **valid_provenance_args,
                    "clusters": [
                        {"cluster_name": "Operations", "thought_items": ["orphan"]},
                        {"cluster_name": "Valid", "thought_items": ["a", "b"]},
                    ],
                },
            )

            # Should succeed, not error
            assert result.isError is not True
            assert result.structuredContent is not None

            # Verify persistence was called
            mock_persist.assert_called_once()

            # Verify Unclustered contains the orphan
            clusters = result.structuredContent.get("clusters", [])
            unclustered = next(
                (c for c in clusters if c["cluster_name"] == "Unclustered"), None
            )
            assert unclustered is not None, "Unclustered cluster should exist"
            assert "orphan" in unclustered["thought_items"]

    @pytest.mark.asyncio
    async def test_orphan_merges_into_existing_unclustered(
        self, valid_provenance_args
    ):
        """
        One orphan with existing Unclustered → orphan merges in.

        Bug that would still pass: If merge logic broke but exemption worked,
        this would fail (merge path guard).
        """
        with patch(
            "mcp_server.clarity.tools.organize_thoughts.persist_cluster",
            new_callable=AsyncMock,
        ) as mock_persist:
            mock_persist.return_value = "cluster-123"

            result = await handle(
                user_id="test",
                correlation_id="test",
                arguments={
                    **valid_provenance_args,
                    "clusters": [
                        {"cluster_name": "SingleItem", "thought_items": ["orphan"]},
                        {
                            "cluster_name": "Unclustered",
                            "thought_items": ["existing1", "existing2"],
                        },
                    ],
                },
            )

            assert result.isError is not True
            clusters = result.structuredContent.get("clusters", [])
            unclustered = next(
                (c for c in clusters if c["cluster_name"] == "Unclustered"), None
            )
            assert unclustered is not None
            # Orphan should have been merged into existing Unclustered
            assert "orphan" in unclustered["thought_items"]
            assert "existing1" in unclustered["thought_items"]

    @pytest.mark.asyncio
    async def test_multiple_orphans_no_existing_unclustered(
        self, valid_provenance_args
    ):
        """
        Multiple orphans → Unclustered with ≥2 items (regression guard).

        This path already worked before the fix. Test ensures fix doesn't
        break it.

        Bug that would still pass: Breakage in multi-orphan merge.
        """
        with patch(
            "mcp_server.clarity.tools.organize_thoughts.persist_cluster",
            new_callable=AsyncMock,
        ) as mock_persist:
            mock_persist.return_value = "cluster-123"

            result = await handle(
                user_id="test",
                correlation_id="test",
                arguments={
                    **valid_provenance_args,
                    "clusters": [
                        {"cluster_name": "Cluster1", "thought_items": ["orphan1"]},
                        {"cluster_name": "Cluster2", "thought_items": ["orphan2"]},
                        {"cluster_name": "Valid", "thought_items": ["a", "b"]},
                    ],
                },
            )

            assert result.isError is not True
            clusters = result.structuredContent.get("clusters", [])
            unclustered = next(
                (c for c in clusters if c["cluster_name"] == "Unclustered"), None
            )
            assert unclustered is not None
            assert len(unclustered["thought_items"]) >= 2
            assert "orphan1" in unclustered["thought_items"]
            assert "orphan2" in unclustered["thought_items"]

    @pytest.mark.asyncio
    async def test_model_supplied_unclustered_one_item_passes(
        self, valid_provenance_args
    ):
        """
        Model directly supplies Unclustered with 1 item → passes.

        Exemption applies regardless of how the cluster arose.

        Bug that would still pass: If exemption only applied to repair output.
        """
        with patch(
            "mcp_server.clarity.tools.organize_thoughts.persist_cluster",
            new_callable=AsyncMock,
        ) as mock_persist:
            mock_persist.return_value = "cluster-123"

            result = await handle(
                user_id="test",
                correlation_id="test",
                arguments={
                    **valid_provenance_args,
                    "clusters": [
                        {"cluster_name": "Unclustered", "thought_items": ["solo"]},
                        {"cluster_name": "Valid", "thought_items": ["a", "b"]},
                    ],
                },
            )

            assert result.isError is not True

    @pytest.mark.asyncio
    async def test_lowercase_unclustered_normalized_by_repair(
        self, valid_provenance_args
    ):
        """
        Model supplies "unclustered" (lowercase) single-item → repair normalizes.

        The repair loop orphans all single-item clusters regardless of name,
        then deposits them into exact-literal "Unclustered". Lowercase variant
        becomes orphan → lands in proper "Unclustered".

        Documents why case-sensitive matching is sufficient.

        Bug that would still pass: Case-insensitive validator exemption
        (wouldn't catch normalization breakage).
        """
        with patch(
            "mcp_server.clarity.tools.organize_thoughts.persist_cluster",
            new_callable=AsyncMock,
        ) as mock_persist:
            mock_persist.return_value = "cluster-123"

            result = await handle(
                user_id="test",
                correlation_id="test",
                arguments={
                    **valid_provenance_args,
                    "clusters": [
                        {"cluster_name": "unclustered", "thought_items": ["lowercase"]},
                        {"cluster_name": "Valid", "thought_items": ["a", "b"]},
                    ],
                },
            )

            assert result.isError is not True
            clusters = result.structuredContent.get("clusters", [])

            # lowercase "unclustered" should NOT exist as a cluster
            lowercase_variant = next(
                (c for c in clusters if c["cluster_name"] == "unclustered"), None
            )
            assert lowercase_variant is None, "lowercase 'unclustered' should be repaired away"

            # Proper "Unclustered" should contain the item
            unclustered = next(
                (c for c in clusters if c["cluster_name"] == "Unclustered"), None
            )
            assert unclustered is not None
            assert "lowercase" in unclustered["thought_items"]


# =============================================================================
# Log Assertion Tests (Change B)
# =============================================================================


class TestRepairFailedLogEmission:
    """Tests for Change B: repair_failed log fields."""

    @pytest.fixture
    def valid_provenance_args(self):
        """Common provenance fields for all handle() calls."""
        return {
            "user_thoughts_exhausted_verbatim": "that's it",
            "user_confirmed_no_more_thoughts": True,
            "thoughts_exhausted": True,
        }

    @pytest.mark.asyncio
    async def test_no_applicable_repair_log_fields(self, valid_provenance_args):
        """
        Validation failure with no applicable repair emits correct log fields.

        - event: organize_thoughts.repair_failed
        - reason: no_applicable_repair
        - validation_error_type: populated list

        Bug that would still pass: Log emission not actually tested.
        """
        with patch(
            "mcp_server.clarity.tools.organize_thoughts.logger"
        ) as mock_logger:
            # Payload that fails validation and has no repair strategy
            # (not a list of strings, not a content field, tags already valid)
            result = await handle(
                user_id="test",
                correlation_id="test",
                arguments={
                    **valid_provenance_args,
                    # Clusters with nested structure that fails differently
                    "clusters": [
                        {
                            "cluster_name": "Empty",
                            # Empty - no thought_items, no subclusters
                        }
                    ],
                },
            )

            assert result.isError is True

            # Find the repair_failed log call
            error_calls = [
                call for call in mock_logger.error.call_args_list
                if call[0] and "repair_failed" in call[0][0]
            ]

            assert len(error_calls) >= 1, "repair_failed should be logged"

            # Check the kwargs of the log call
            log_kwargs = error_calls[0][1]
            assert log_kwargs.get("reason") == "no_applicable_repair"
            assert "validation_error_type" in log_kwargs
            assert isinstance(log_kwargs["validation_error_type"], list)
            assert len(log_kwargs["validation_error_type"]) > 0

    @pytest.mark.asyncio
    async def test_unrecognizable_payload_logs_no_applicable_repair(
        self, valid_provenance_args
    ):
        """
        Genuinely unrecognizable payload logs reason=no_applicable_repair.

        Bug that would still pass: If old reason="unrecognized_format" remained.

        NOTE: Uses list of non-dict/non-string items to avoid pre-existing
        KeyError bug when clusters is a dict (flagged as separate backlog item).
        """
        with patch(
            "mcp_server.clarity.tools.organize_thoughts.logger"
        ) as mock_logger:
            result = await handle(
                user_id="test",
                correlation_id="test",
                arguments={
                    **valid_provenance_args,
                    # List of non-dict items - triggers validation failure,
                    # no repair strategy matches (not strings, not dicts)
                    "clusters": [123, 456],
                },
            )

            assert result.isError is True

            error_calls = [
                call for call in mock_logger.error.call_args_list
                if call[0] and "repair_failed" in call[0][0]
            ]

            assert len(error_calls) >= 1
            log_kwargs = error_calls[0][1]
            assert log_kwargs.get("reason") == "no_applicable_repair"


# =============================================================================
# Negative Integration Test
# =============================================================================


class TestNegativeRoundTrip:
    """Negative tests ensuring error paths still work."""

    @pytest.fixture
    def valid_provenance_args(self):
        return {
            "user_thoughts_exhausted_verbatim": "that's it",
            "user_confirmed_no_more_thoughts": True,
            "thoughts_exhausted": True,
        }

    @pytest.mark.asyncio
    async def test_unrecognizable_clusters_returns_invalid_params_error(
        self, valid_provenance_args
    ):
        """
        Payload with genuinely no recognizable clusters returns invalid-params.

        Bug that would still pass: If error path changed behavior.
        """
        result = await handle(
            user_id="test",
            correlation_id="test",
            arguments={
                **valid_provenance_args,
                "clusters": "not an array",
            },
        )

        assert result.isError is True
        # The error text should contain the invalid-params structure
        assert len(result.content) > 0
        assert "Invalid input format" in result.content[0].text
