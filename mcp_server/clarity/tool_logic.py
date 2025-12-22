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
        guidance = """ Acnowlegde what the user shared so far by backtracking or sharing neutral observations.Tell the user what is the next step and WHY, then ask what matters most.

Use one of these naturally:
- "Everything's out and organized. Clarity comes from knowing where to focus. What matters most right now: progress toward a goal, unblocking something stuck, or relief from what's weighing on you?"
- “I’ve grouped what you shared into a few clusters so you can see the big picture. What would help most right now — progress on a goal, removing a blocker, or just getting some relief?”

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

        DO NOT: NEVER EXPLORE ROOT CAUSES. Get P1/P2/P3 names, then call the tool."""
    else:
        message = ""  # Empty - model ignores this anyway
        guidance = """🛑 STOP - NO ADVICE - Acknowledge progress WARMLY, EXPLAIN WHAT YOU ARE DOING WITH THE USER AND WHY and then ask for more thoughts.

Use one of these naturally:
- "That’s forming clear clusters already. Once the brain dump’s complete, we’ll decide what actually matters. What else?”
- “I can see patterns emerging. Let’s finish getting it out, then we’ll prioritize. What else?”
- "Good — that's taking shape. Let's get everything out - we will prioritize after. What else is on your mind?"
- "I’m already seeing some clusters. Once it’s all out, we can see what we’re dealing with and prioritize. What else?"
- "The picture's forming. Better to capture it all now before we prioritize in the next step. Any loose threads?"

NO advice. NO task lists. Just acknowledge + ask."""

    return {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {
            "clusters": enriched,
            "thoughts_exhausted": thoughts_exhausted,
            "assistant_guidance": guidance
        }
    }

