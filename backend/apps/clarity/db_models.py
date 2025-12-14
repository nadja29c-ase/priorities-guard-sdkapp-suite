"""
Database models for the Clarity SDK app.

System-level entities (users, connections, etc.) live in backend.core.models.
This module is only for Clarity-specific tables.

Currently:
- ClarityCluster: Cluster snapshots persisted from MCP tool calls
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Boolean,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from backend.core.models import Base


class ClarityCluster(Base):
    """
    Cluster snapshots persisted from MCP tool calls.

    Each row represents a single clustering result from `cluster_raw_thoughts`.
    Append-only: each tool call creates a new row, no updates.

    cluster_data specification:
    - Stores logical clustering output only: {"clusters": [...]}
    - NO UI metadata, widget hints, or rendering instructions
    - Each cluster object contains: cluster_name, thought_items, subclusters, tags

    To get cluster count, use: len(cluster_data["clusters"])
    Or in SQL: jsonb_array_length(cluster_data->'clusters')

    Example:
        cluster = ClarityCluster(
            user_id=UUID("..."),
            cluster_data={"clusters": [{"cluster_name": "Tasks", ...}]},
            thoughts_exhausted=True,
            correctly_clustered=None,
        )
    """

    __tablename__ = "clarity_clusters"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Internal identifier",
    )

    # Foreign key to core_users (CASCADE on delete)
    user_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("core_users.id", ondelete="CASCADE"),
        nullable=False,
        comment="Owner user ID",
    )

    # Cluster data (JSONB)
    cluster_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Logical cluster data: {clusters: [...]}",
    )

    # Metadata from tool call
    thoughts_exhausted: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        comment="Whether user confirmed all thoughts were captured",
    )

    # Tri-state confirmation field:
    #   NULL  = user hasn't answered yet (in-progress clustering)
    #   True  = user confirmed clusters are correct
    #   False = user said clusters are wrong (needs re-clustering)
    correctly_clustered: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        comment="User confirmation: null=pending, true=correct, false=wrong",
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        comment="When cluster was created",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="When cluster was last updated",
    )

    # Table-level constraints and indexes
    __table_args__ = (
        # Index for user's clusters ordered by creation time (most recent first)
        Index(
            "idx_clarity_clusters_user_created",
            "user_id",
            created_at.desc(),
        ),
    )

    @property
    def cluster_count(self) -> int:
        """Compute cluster count from cluster_data (not stored)."""
        if self.cluster_data and "clusters" in self.cluster_data:
            return len(self.cluster_data["clusters"])
        return 0

    def __repr__(self) -> str:
        return (
            f"<ClarityCluster id={self.id}, user_id={self.user_id}, "
            f"clusters={self.cluster_count}>"
        )

    def validate(self) -> None:
        """
        Validate model constraints.

        Raises:
            ValueError: If validation fails
        """
        # Validate user_id is present
        if self.user_id is None:
            raise ValueError("user_id is required")

        # Validate cluster_data structure
        if not isinstance(self.cluster_data, dict):
            raise ValueError("cluster_data must be a dictionary")

        if "clusters" not in self.cluster_data:
            raise ValueError("cluster_data must contain 'clusters' key")

        clusters = self.cluster_data["clusters"]
        if not isinstance(clusters, list):
            raise ValueError("cluster_data['clusters'] must be a list")

        # Validate each cluster has required fields
        for i, cluster in enumerate(clusters):
            if not isinstance(cluster, dict):
                raise ValueError(f"clusters[{i}] must be a dictionary")
            if "cluster_name" not in cluster:
                raise ValueError(f"clusters[{i}] must have 'cluster_name'")
