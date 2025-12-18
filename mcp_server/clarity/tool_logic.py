"""
Clarity tool logic - V5 (Widget Integration).

ChatGPT clusters and reasons BEFORE calling each tool.
Tools only format/validate - no AI logic here.
"""


def enrich_clusters(clusters: list[dict]) -> list[dict]:
    """
    Add sum_thought_items to clusters and subclusters.

    Used by:
    - organize_thoughts: enrich before returning to widget
    - load_saved_board: enrich persisted data before display
    - read_saved_board: enrich persisted data before returning

    Args:
        clusters: List of cluster dicts from ChatGPT or persistence

    Returns:
        Enriched clusters with sum_thought_items added
    """
    enriched = []

    for c in clusters:
        subclusters = c.get("subclusters", [])
        thought_items = c.get("thought_items", [])
        tags = c.get("tags", [])

        # Enrich subclusters if present (include tags and priority)
        enriched_subclusters = [
            {
                "subcluster_name": sc.get("subcluster_name", ""),
                "thought_items": sc.get("thought_items", []),
                "sum_thought_items": len(sc.get("thought_items", [])),
                "tags": sc.get("tags", []),
                "priority": sc.get("priority"),  # Preserve priority field
            }
            for sc in subclusters
        ]

        # Total = direct items + all subcluster items
        subcluster_total = sum(len(sc.get("thought_items", [])) for sc in subclusters)
        total_items = len(thought_items) + subcluster_total

        enriched.append({
            "cluster_name": c.get("cluster_name", ""),
            "thought_items": thought_items,
            "subclusters": enriched_subclusters,
            "sum_thought_items": total_items,
            "tags": tags,
            "priority": c.get("priority"),  # Preserve priority field
        })

    return enriched


def organize_thoughts(clusters: list[dict]) -> dict:
    """
    Format business thought clusters that ChatGPT has already identified.

    Args:
        clusters: List of clusters with:
            - 'cluster_name' and 'thought_items' (flat structure), or
            - 'cluster_name' and 'subclusters' (nested structure), or
            - both (mixed: ungrouped items + grouped subclusters)
            - optional 'tags' for behavioral hints

    Returns:
        Widget-compatible output with content and structuredContent.
    """
    enriched = enrich_clusters(clusters)

    return {
        "content": [{"type": "text", "text": "I've organized your thoughts into clusters."}],
        "structuredContent": {
            "clusters": enriched
        }
    }


'''#def identify_most_relevant_clusters(
    selected_cluster_names: list[str],
    clusters: list[dict]
#) -> dict:
    """
    Filter to only the clusters the user selected as most relevant.

    Args:
        selected_cluster_names: Names of clusters user selected.
        clusters: Enriched clusters from cluster_raw_thoughts output.

    Returns:
        Filtered top_clusters.
    """
    return {
        "top_clusters": [
            c for c in clusters
            if c["name"] in selected_cluster_names
        ]
    }


#def specify_next_steps(top_clusters: list[dict]) -> dict:
    """
    Generate next steps from the user's top clusters.

    Args:
        top_clusters: Filtered clusters from identify_most_relevant_clusters.

    Returns:
        Next steps and clarity summary.
    """
    steps = []
    for cluster in top_clusters[:3]:
        for item in cluster.get("items", [])[:2]:
            steps.append({
                "step": f"Work on: {item}",
                "source_cluster": cluster["name"],
                "effort": "low" if len(item) < 30 else "medium"
            })
    return {
        "next_steps": steps[:5],
        "clarity_summary": f"Focus on {', '.join(c['name'] for c in top_clusters[:3])}"
    }
'''