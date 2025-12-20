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
        message = "Here's your Clarity Board. Want to create more clarity and prioritize? Tell me which clusters matter most to you right now."
        guidance = """Acknowledge the user's feelings / thoughts and ask: 'What matters most right now — making progress toward a goal, unblocking something stuck, or getting relief from what's weighing on you?'

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

        variants = [
            "Everything's out and organized — you can see the full picture now. So, what matters most right now: making progress toward a goal, unblocking something stuck, or getting relief from what's weighing on you?",
            "You've done the hard part — it's all out of your head. Now let's focus. What would help most right now: moving toward a goal, clearing a blocker, or just getting some relief?",
            "Your Clarity Board is ready. Before we prioritize, tell me: are you chasing a goal, trying to get unstuck, or just need some weight off your shoulders?",
            "Your scattered thoughts are now visible and grouped. That's the first step to cutting through the noise. Now tell me, what would help you most right now: achieving a specific goal? getting unstuck? finding relief?"
        ]
    else:
        message = "What else is on your mind?"
        guidance = "🛑 STOP - NO ADVICE - Instead, acknowledge what's been captured, note progress toward clarity, then ask for more thought items. Stay warm."
        variants = [
            "Good — that's already taking shape. Let's get everything out so nothing keeps spinning in your head. What else?",
            "Awesome, you're getting it out of your head and onto the board — that's how the overwhelm shrinks. Anything else?",
            "More clarity with each one! We want the full picture before prioritizing. What other thoughts are taking up space?",
            "The picture's forming. Better to capture it all now than have it pop up later. Any loose threads?",
            "Great, we're building your Clarity Board. The more complete it is, the better we can prioritize. What else is on your mind?",
            "That's a few clusters already. Once it's all out, you can actually see what you're dealing with. What else is bouncing around?",
            "Amazing, let's keep going and make space in your mind for what really matters. Any other thoughts to add to the board?",
            "Nice. Thoughts dumped, clusters formed — you can actually see what you're dealing with now. Any loose threads before we focus in?",
            "That's your board taking shape — no more spinning in your head. Let's capture anything else so we can prioritize with the full picture. What other thoughts are taking up space?"
        ]

    result = {
        "content": [{"type": "text", "text": message}],
        "structuredContent": {
            "clusters": enriched,
            "thoughts_exhausted": thoughts_exhausted,
            "assistant_guidance": guidance
        }
    }

    if variants:
        result["structuredContent"]["question_variants"] = variants

    return result

