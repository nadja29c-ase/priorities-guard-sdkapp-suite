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


def organize_thoughts(clusters: list[dict], thoughts_exhausted: bool = False) -> dict:
    """
    Format business thought clusters that ChatGPT has already identified.

    Args:
        clusters: List of clusters with:
            - 'cluster_name' and 'thought_items' (flat structure), or
            - 'cluster_name' and 'subclusters' (nested structure), or
            - both (mixed: ungrouped items + grouped subclusters)
            - optional 'tags' for behavioral hints
        thoughts_exhausted: True if user confirmed they're done sharing thoughts

    Returns:
        Widget-compatible output with content and structuredContent.
    """
    enriched = enrich_clusters(clusters)

    if thoughts_exhausted:
        message = "Here's your Clarity board. Want to prioritize? Tell me which clusters matter most to you."
        guidance = "Ask: 'Which clusters feel most important to you?' Do not explain, advise, or suggest actions."
    else:
        message = "🛑 STOP. Ask only: 'What else is on your mind?' — say nothing else."
        guidance = "Ask only: 'What else is on your mind?' Do not explain, advise, or organize further."

    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {
            "clusters": enriched,
            "thoughts_exhausted": thoughts_exhausted,
            "assistant_guidance": guidance
        }
    }

