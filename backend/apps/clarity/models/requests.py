"""
Request models for Clarity API endpoints.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, model_validator


class CreateClusterRequest(BaseModel):
    """Request body for POST /api/clarity/clusters."""

    cluster_data: dict[str, Any]  # Must contain "clusters" key
    content_hash: str | None = None  # SHA256 hash for saved state detection
    # DEPRECATED fields - accepted for backward compatibility but ignored
    thoughts_exhausted: bool | None = None  # Always ignored, kept for API compat
    correctly_clustered: bool | None = None  # Always ignored, kept for API compat

    @model_validator(mode="after")
    def validate_cluster_data(self) -> "CreateClusterRequest":
        """Validate cluster_data has required structure.

        VALIDATION BOUNDARY:
            This validates MINIMAL STRUCTURAL VIABILITY only:
            - cluster_data contains "clusters" key
            - clusters is a list
            - each cluster is a dict with "cluster_name"

            This does NOT validate:
            - thought_items, subclusters, tags
            - cluster object shape beyond name
            - semantic correctness

            Semantic validation is the MCP tool's responsibility.
            The LLM controls cluster content; backend is a passthrough store.

            Do NOT add deep validation here - it would break MCP flexibility
            and couple backend to LLM prompt changes.
        """
        if "clusters" not in self.cluster_data:
            raise ValueError("cluster_data must contain 'clusters' key")

        clusters = self.cluster_data["clusters"]
        if not isinstance(clusters, list):
            raise ValueError("cluster_data['clusters'] must be a list")

        # NOTE: Empty clusters list IS allowed.
        # Valid use case: user starts brain dump but hasn't clustered yet.
        # MCP tool handles empty state appropriately.

        # Validate each cluster has cluster_name
        for i, cluster in enumerate(clusters):
            if not isinstance(cluster, dict):
                raise ValueError(f"cluster_data['clusters'][{i}] must be a dict")
            if "cluster_name" not in cluster:
                raise ValueError(
                    f"cluster_data['clusters'][{i}] must have 'cluster_name'"
                )

        return self


class CreateClusterResponse(BaseModel):
    """Response body for POST /api/clarity/clusters."""

    cluster_id: UUID
    created_at: datetime


class GetClusterResponse(BaseModel):
    """Response body for GET /api/clarity/clusters.

    TIMESTAMP SEMANTICS:
        created_at is the SNAPSHOT timestamp, reset on each POST.
        It does NOT represent "first creation time" - each POST is a fresh snapshot.
        This matches replace-latest semantics (single row per user).

        updated_at is intentionally omitted (would always equal created_at).
    """

    cluster_id: UUID
    cluster_data: dict[str, Any]  # {"clusters": [...]}
    created_at: datetime  # Snapshot timestamp (reset on each upsert)
    content_hash: str | None = None  # SHA256 hash for saved state detection
    # DEPRECATED fields - returned for backward compatibility with fixed values
    thoughts_exhausted: bool = False  # Always False, kept for API compat
    correctly_clustered: bool | None = None  # Always None, kept for API compat


class DeleteDataRequest(BaseModel):
    """Request body for DELETE /api/clarity/data."""
    confirm: bool = False  # Must be True to execute deletion


class DeleteDataResponse(BaseModel):
    """Response body for DELETE /api/clarity/data.

    Statuses:
    - deleted: Data was successfully deleted
    - no_data: No data found for user (idempotent success)
    """
    status: str  # "deleted" or "no_data"
    message: str
    deleted: dict[str, int] | None = None  # {"clarity_clusters": N} when status="deleted"
