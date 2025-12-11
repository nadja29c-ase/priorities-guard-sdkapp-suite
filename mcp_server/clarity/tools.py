"""
Clarity tool logic - V5 (Widget Integration).

ChatGPT clusters and reasons BEFORE calling each tool.
Tools only format/validate - no AI logic here.
"""


def cluster_raw_thoughts(clusters: list[dict]) -> dict:
    """
    Format business thought clusters that ChatGPT has already identified.

    Args:
        clusters: List of clusters with 'name' and 'thought_items' fields.

    Returns:
        Widget-compatible output with content and structuredContent.
    """
    enriched = [
        {
            "name": c["name"],
            "thought_items": c["thought_items"],
            "sum_thought_items": len(c["thought_items"])
        }
        for c in clusters
    ]

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