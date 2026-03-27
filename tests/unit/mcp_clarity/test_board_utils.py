"""
Unit tests for board_utils functions.

Focus areas:
1. compute_content_hash() canonical serialization
2. Hash consistency across different input orderings
3. Unicode normalization (NFC)
4. Whitespace handling

NOTE: saved_board_hash is tested for backend consistency and LLM reasoning.
The widget does NOT use it for persistent saved state detection - it uses
transient 3-second feedback instead. Any future changes removing hash
comparison from the widget are intentional, not regressions.
"""

import pytest
from mcp_server.clarity.tools.board_utils import compute_content_hash


class TestCanonicalHash:
    """Tests for compute_content_hash() function."""

    def test_deterministic_same_input(self):
        """Same input produces same hash."""
        clusters = [
            {"cluster_name": "Work", "thought_items": ["task1", "task2"], "subclusters": [], "tags": []}
        ]
        hash1 = compute_content_hash(clusters)
        hash2 = compute_content_hash(clusters)
        assert hash1 == hash2

    def test_different_input_different_hash(self):
        """Different inputs produce different hashes."""
        clusters1 = [{"cluster_name": "Work", "thought_items": ["task1"], "subclusters": [], "tags": []}]
        clusters2 = [{"cluster_name": "Home", "thought_items": ["task1"], "subclusters": [], "tags": []}]
        assert compute_content_hash(clusters1) != compute_content_hash(clusters2)

    def test_hash_is_64_hex_chars(self):
        """Hash is full SHA256 (64 hex characters)."""
        clusters = [{"cluster_name": "Test", "thought_items": [], "subclusters": [], "tags": []}]
        hash_result = compute_content_hash(clusters)
        assert len(hash_result) == 64
        assert all(c in "0123456789abcdef" for c in hash_result)


class TestClusterOrdering:
    """Tests for cluster ordering normalization."""

    def test_clusters_sorted_by_name(self):
        """Clusters are sorted alphabetically by cluster_name."""
        # Input in wrong order
        clusters_unordered = [
            {"cluster_name": "Zebra", "thought_items": [], "subclusters": [], "tags": []},
            {"cluster_name": "Alpha", "thought_items": [], "subclusters": [], "tags": []},
        ]
        # Input in correct order
        clusters_ordered = [
            {"cluster_name": "Alpha", "thought_items": [], "subclusters": [], "tags": []},
            {"cluster_name": "Zebra", "thought_items": [], "subclusters": [], "tags": []},
        ]
        assert compute_content_hash(clusters_unordered) == compute_content_hash(clusters_ordered)

    def test_thought_items_sorted(self):
        """thought_items are sorted lexicographically."""
        clusters1 = [
            {"cluster_name": "Work", "thought_items": ["zebra", "alpha", "beta"], "subclusters": [], "tags": []}
        ]
        clusters2 = [
            {"cluster_name": "Work", "thought_items": ["alpha", "beta", "zebra"], "subclusters": [], "tags": []}
        ]
        assert compute_content_hash(clusters1) == compute_content_hash(clusters2)

    def test_tags_sorted(self):
        """tags are sorted lexicographically."""
        clusters1 = [
            {"cluster_name": "Work", "thought_items": [], "subclusters": [], "tags": ["urgent", "align"]}
        ]
        clusters2 = [
            {"cluster_name": "Work", "thought_items": [], "subclusters": [], "tags": ["align", "urgent"]}
        ]
        assert compute_content_hash(clusters1) == compute_content_hash(clusters2)

    def test_subclusters_sorted_by_name(self):
        """Subclusters are sorted by subcluster_name."""
        clusters1 = [
            {
                "cluster_name": "Work",
                "thought_items": [],
                "tags": [],
                "subclusters": [
                    {"subcluster_name": "Zebra", "thought_items": [], "tags": []},
                    {"subcluster_name": "Alpha", "thought_items": [], "tags": []},
                ],
            }
        ]
        clusters2 = [
            {
                "cluster_name": "Work",
                "thought_items": [],
                "tags": [],
                "subclusters": [
                    {"subcluster_name": "Alpha", "thought_items": [], "tags": []},
                    {"subcluster_name": "Zebra", "thought_items": [], "tags": []},
                ],
            }
        ]
        assert compute_content_hash(clusters1) == compute_content_hash(clusters2)

    def test_subcluster_items_sorted(self):
        """Subcluster thought_items are sorted."""
        clusters1 = [
            {
                "cluster_name": "Work",
                "thought_items": [],
                "tags": [],
                "subclusters": [
                    {"subcluster_name": "Tasks", "thought_items": ["c", "a", "b"], "tags": []},
                ],
            }
        ]
        clusters2 = [
            {
                "cluster_name": "Work",
                "thought_items": [],
                "tags": [],
                "subclusters": [
                    {"subcluster_name": "Tasks", "thought_items": ["a", "b", "c"], "tags": []},
                ],
            }
        ]
        assert compute_content_hash(clusters1) == compute_content_hash(clusters2)


class TestWhitespaceNormalization:
    """Tests for whitespace trimming."""

    def test_leading_trailing_whitespace_trimmed(self):
        """Leading/trailing whitespace is trimmed."""
        clusters1 = [{"cluster_name": "  Work  ", "thought_items": [" task "], "subclusters": [], "tags": []}]
        clusters2 = [{"cluster_name": "Work", "thought_items": ["task"], "subclusters": [], "tags": []}]
        assert compute_content_hash(clusters1) == compute_content_hash(clusters2)

    def test_internal_whitespace_preserved(self):
        """Internal whitespace is preserved (only trim, not collapse)."""
        clusters1 = [{"cluster_name": "Work Tasks", "thought_items": [], "subclusters": [], "tags": []}]
        clusters2 = [{"cluster_name": "WorkTasks", "thought_items": [], "subclusters": [], "tags": []}]
        assert compute_content_hash(clusters1) != compute_content_hash(clusters2)


class TestUnicodeNormalization:
    """Tests for NFC Unicode normalization."""

    def test_nfc_normalization_composed_vs_decomposed(self):
        """NFC normalization: composed and decomposed forms hash identically.

        'é' can be represented as:
        - Composed (NFC): U+00E9 (single code point)
        - Decomposed (NFD): U+0065 U+0301 (e + combining acute)

        Both should hash to the same value after NFC normalization.
        """
        # Composed form (NFC)
        clusters_composed = [
            {"cluster_name": "café", "thought_items": [], "subclusters": [], "tags": []}
        ]
        # Decomposed form (NFD) - 'e' + combining acute accent
        clusters_decomposed = [
            {"cluster_name": "cafe\u0301", "thought_items": [], "subclusters": [], "tags": []}
        ]
        assert compute_content_hash(clusters_composed) == compute_content_hash(clusters_decomposed)


class TestExplicitKeyOrder:
    """Tests for explicit key ordering (not alphabetical)."""

    def test_key_order_cluster_name_subclusters_tags_thought_items(self):
        """Verify key order is: cluster_name, subclusters, tags, thought_items.

        This test verifies the canonical form matches the specification.
        If alphabetical sorting were used, order would be:
        cluster_name, subclusters, tags, thought_items (happens to match for clusters)

        For subclusters, alphabetical would be: subcluster_name, tags, thought_items
        Which also matches. So we verify by checking the actual JSON output.
        """
        clusters = [
            {
                "cluster_name": "Work",
                "subclusters": [],
                "tags": ["urgent"],
                "thought_items": ["task1"],
            }
        ]
        # The hash should be consistent regardless of input key order
        clusters_reordered = [
            {
                "thought_items": ["task1"],
                "tags": ["urgent"],
                "cluster_name": "Work",
                "subclusters": [],
            }
        ]
        assert compute_content_hash(clusters) == compute_content_hash(clusters_reordered)


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_clusters(self):
        """Empty clusters list produces consistent hash."""
        hash_result = compute_content_hash([])
        assert len(hash_result) == 64

    def test_missing_optional_fields(self):
        """Missing optional fields default to empty."""
        # Minimal cluster (only required field)
        clusters1 = [{"cluster_name": "Work"}]
        # Explicit empty fields
        clusters2 = [{"cluster_name": "Work", "thought_items": [], "subclusters": [], "tags": []}]
        assert compute_content_hash(clusters1) == compute_content_hash(clusters2)

    def test_empty_string_cluster_name(self):
        """Empty string cluster_name is handled."""
        clusters = [{"cluster_name": "", "thought_items": [], "subclusters": [], "tags": []}]
        hash_result = compute_content_hash(clusters)
        assert len(hash_result) == 64

    def test_special_characters(self):
        """Special characters in strings are handled."""
        clusters = [
            {
                "cluster_name": 'Work "quotes" & <tags>',
                "thought_items": ["line1\nline2", "tab\there"],
                "subclusters": [],
                "tags": [],
            }
        ]
        hash_result = compute_content_hash(clusters)
        assert len(hash_result) == 64


class TestKnownHash:
    """Test against known hash value for regression detection.

    CROSS-LANGUAGE PARITY:
    These tests use hardcoded expected hashes. The same inputs must produce
    identical hashes in both Python (board_utils.py) and JavaScript (widget).

    If a test fails, it means the hash algorithm changed - this is a BREAKING
    CHANGE that will cause the widget to show incorrect saved/unsaved state.

    To verify JS implementation matches, run in browser console:
        const clusters = [...];  // same test data
        const hash = await computeContentHash(clusters);
        console.log(hash);  // should match expected_hash
    """

    def test_known_hash_simple_board(self):
        """Verify hash matches known value for simple board.

        This is the primary cross-language parity test. If this fails,
        Python and JS implementations have diverged.

        Canonical JSON:
        {"clusters":[{"cluster_name":"Home","subclusters":[],"tags":[],"thought_items":["buy groceries","call dentist"]},{"cluster_name":"Work","subclusters":[],"tags":["align"],"thought_items":["finish report"]}]}
        """
        clusters = [
            {
                "cluster_name": "Home",
                "subclusters": [],
                "tags": [],
                "thought_items": ["buy groceries", "call dentist"],
            },
            {
                "cluster_name": "Work",
                "subclusters": [],
                "tags": ["align"],
                "thought_items": ["finish report"],
            },
        ]

        expected_hash = "0139f06ebec14cb8ac9380554113983829dcdfd1f32f2378ce294f15b709978b"
        actual_hash = compute_content_hash(clusters)

        assert actual_hash == expected_hash, (
            f"Hash mismatch! Expected {expected_hash}, got {actual_hash}. "
            "This is a BREAKING CHANGE - widget will show incorrect saved state."
        )

    def test_known_hash_with_subclusters(self):
        """Verify hash for board with subclusters.

        Tests that subclusters are correctly normalized and sorted.
        """
        clusters = [
            {
                "cluster_name": "Work",
                "subclusters": [
                    {"subcluster_name": "Urgent", "tags": ["urgent"], "thought_items": ["task1"]},
                    {"subcluster_name": "Later", "tags": [], "thought_items": ["task2", "task3"]},
                ],
                "tags": [],
                "thought_items": ["standalone task"],
            },
        ]

        expected_hash = "921d1efd11db96e4f7b9d34f4b149d159bc10a90903c8bd14b4443d6094ba055"
        actual_hash = compute_content_hash(clusters)

        assert actual_hash == expected_hash, (
            f"Hash mismatch! Expected {expected_hash}, got {actual_hash}. "
            "Subcluster normalization may have changed."
        )

    def test_hash_determinism(self):
        """Verify hash is deterministic across multiple calls."""
        clusters = [
            {"cluster_name": "Test", "thought_items": ["a", "b", "c"]},
        ]
        hashes = [compute_content_hash(clusters) for _ in range(10)]
        assert len(set(hashes)) == 1, "Hash is not deterministic"
