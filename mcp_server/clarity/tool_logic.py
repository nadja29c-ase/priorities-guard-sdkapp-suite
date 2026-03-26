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
        guidance = """🛑 STOP. Do NOT give advice. Do NOT list options as bullet points. Do NOT use headers or formatting.

STEP 1 — ACKNOWLEDGE WHAT YOU SEE (2-3 sentences max):
Before asking anything, briefly reflect on what the clusters reveal. Name the tensions or themes you notice — e.g. high-stakes deep work competing with admin backlog, a mix of execution and decision-making, clusters that signal different mental modes. Keep it observational, not therapeutic.

Step 2 — Tags (1 sentence): If tags are present, mention them briefly — they flag clusters that need a different kind of attention beyond normal execution (like a decision that needs to be made, something to research first, or work to delegate). The user can change them.

STEP 3 — BRIDGE TO PRIORITIZATION (1 sentence):
Add a short, direct bridge — not coaching language, not therapeutic. Something like: "Now let's make sure your attention goes to the 1-3 things that actually matter right now." Keep it grounded and action-oriented.

STEP 4 — ASK THE CRITERION QUESTION:
Say EXACTLY this — do not rephrase, do not add bullet points, do not change the structure. Bold the question as shown:
"**What matters most right now — progress toward a goal, removing a blocker, or getting some relief?**"

Wait for the user's answer. Store it in user_prioritization_criterion_verbatim.
Then ask which cluster, subcluster, or specific item on the board fits that criterion best. A cluster name is fine as a starting point — but if the user names a cluster, ask if there is a more specific subcluster or item within it that is the real focus, or if the whole cluster is what they mean. What the user confirms becomes priority number 1.
Call prioritize_clusters immediately when the user names it."""
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

