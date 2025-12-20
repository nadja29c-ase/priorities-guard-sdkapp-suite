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
        message = ""  # Empty - model ignores this anyway
        guidance = """Acknowledge the user's work, then ask what matters most.

Use one of these naturally:
- "Everything's out and organized. Clarity comes from knowing where to focus. What matters most right now: progress toward a goal, unblocking something stuck, or relief from what's weighing on you?"
- "You've done the hard part — it's all out. What would help most: moving toward a goal, clearing a blocker, or getting some relief?"
- "Your board is ready. Are you chasing a goal, trying to get unstuck, or just need weight off your shoulders?"

EXAMPLE FLOW:
        User: 'Relief, I guess'
        You: 'That makes sense.Looking at your board — which cluster would bring the MOST relief if you made progress there RIGHT NOW?'
        User: 'Billing probably'
        You: 'Billing - got it. That sounds like your priority number 1 (P1). Do you agree?'
        User: 'Yes'
        You: 'Great, already clearer. What about P2 — anything else that would lighten the load?' 
        User: 'Client Communication'  
        You: 'Good. You're creating clear focus areas — that alone starts to quiet the noise. Do you feel like adding a third priority? If so, what would be your P3?'
        User: 'Maybe Project Oversight'→ Call prioritize_clusters display at least P1, optionally P2, P3.

        DO NOT: Explore root causes. Get P1/P2/P3 names, then call the tool."""
    else:
        message = ""  # Empty - model ignores this anyway
        guidance = """🛑 STOP - NO ADVICE - Acknowledge progress warmly, then ask for more thoughts.

Use one of these naturally:
- "Good — that's taking shape. Let's get everything out. What else is on your mind?"
- "You're getting it out of your head — that's how overwhelm shrinks. Anything else?"
- "The picture's forming. Better to capture it all now. Any loose threads?"
- "That's a few clusters already. Once it's all out, you can see what you're dealing with. What else?"

No advice. No task lists. Just acknowledge + ask."""

    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {
            "clusters": enriched,
            "thoughts_exhausted": thoughts_exhausted,
            "assistant_guidance": guidance
        }
    }

