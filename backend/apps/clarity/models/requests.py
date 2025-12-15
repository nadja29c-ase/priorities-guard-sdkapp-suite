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
    thoughts_exhausted: bool
    correctly_clustered: bool | None = None

    @model_validator(mode="after")
    def validate_cluster_data(self) -> "CreateClusterRequest":
        """Validate cluster_data has required structure."""
        if "clusters" not in self.cluster_data:
            raise ValueError("cluster_data must contain 'clusters' key")

        clusters = self.cluster_data["clusters"]
        if not isinstance(clusters, list):
            raise ValueError("cluster_data['clusters'] must be a list")

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
    """Response body for GET /api/clarity/clusters."""

    cluster_id: UUID
    cluster_data: dict[str, Any]  # {"clusters": [...]}
    thoughts_exhausted: bool
    correctly_clustered: bool | None
    created_at: datetime
