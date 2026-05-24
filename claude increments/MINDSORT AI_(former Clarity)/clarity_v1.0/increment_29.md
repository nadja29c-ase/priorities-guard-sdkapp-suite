Claude Code Briefing: Fix Priority Not Persisting Through Save/Load

Problem:
When user saves board with priorities set, then loads it later, priorities are missing. Root cause: save_board.py INPUT_SCHEMA doesn't include priority field, so ChatGPT doesn't pass priority data when calling the tool.
Files to modify:

/mcp_server/clarity/tools/save_board.py

Changes to INPUT_SCHEMA:
Add priority field to cluster object properties:
python"priority": {
    "type": ["object", "null"],
    "description": "Priority assignment on this cluster (pass through from previous output)",
    "properties": {
        "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
        "reason": {"type": "string", "enum": ["blocker", "goal-aligned"]}
    }
}
Add priority field to subcluster object properties (inside subclusters.items.properties):
python"priority": {
    "type": ["object", "null"],
    "description": "Priority assignment on this subcluster (pass through from previous output)",
    "properties": {
        "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
        "reason": {"type": "string", "enum": ["blocker", "goal-aligned"]}
    }
}
Also add priority to thought_items object format (the oneOf object option):
python{
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "priority": {
            "type": ["object", "null"],
            "properties": {
                "rank": {"type": "string", "enum": ["P1", "P2", "P3"]},
                "reason": {"type": "string", "enum": ["blocker", "goal-aligned"]}
            }
        }
    }
}

Verification:
After fix, test flow:

Create board with organize_thoughts
Set P1 with prioritize_clusters
Save board
New conversation → load_saved_board
Priority should appear on loaded board

Unit tests:

save_board accepts clusters with priority field
save_board persists priority to database
load_saved_board returns priority from database

Integration test:

Full round-trip: organize → prioritize → save → load → verify priority intact