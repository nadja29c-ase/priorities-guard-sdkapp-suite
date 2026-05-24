Claude Code Briefing: Shared Cluster Enrichment
Problem
load_saved_board returns raw clusters without sum_thought_items. Widget shows "—" instead of item counts.
Fix
Extract enrichment to shared utility. Use in both tools.
1. Create/update mcp_server/clarity/tool_logic.py
Add function:
pythondef enrich_clusters(clusters: list[dict]) -> list[dict]:
    """Add sum_thought_items to clusters and subclusters."""
    enriched = []
    for c in clusters:
        thought_items = c.get("thought_items", [])
        subclusters = c.get("subclusters", [])
        
        enriched_subclusters = [
            {**sc, "sum_thought_items": len(sc.get("thought_items", []))}
            for sc in subclusters
        ]
        
        subcluster_total = sum(len(sc.get("thought_items", [])) for sc in subclusters)
        
        enriched.append({
            **c,
            "subclusters": enriched_subclusters,
            "sum_thought_items": len(thought_items) + subcluster_total,
        })
    return enriched
Refactor existing organize_thoughts to use it.
2. Update load_saved_board.py
pythonfrom ..tool_logic import enrich_clusters

# After extracting clusters from persistence:
clusters = enrich_clusters(clusters)
3. Update read_saved_board.py
Same change - enrich before returning.
Test

load_saved_board → widget shows item counts
organize_thoughts → widget shows item counts (no regression)
