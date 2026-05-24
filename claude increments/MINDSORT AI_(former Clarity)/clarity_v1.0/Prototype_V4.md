Goal
Replace single create_clarity tool with 3 sequential tools. GPT clusters and reasons BEFORE calling each tool. Tools only format/validate.

Tool 1: cluster_raw_thoughts
Description:
Format business thought clusters that ChatGPT has already identified. 
ChatGPT MUST cluster the user's thoughts BEFORE calling this tool.
Do NOT call this tool until you have presented clusters to the user.
Input:
json{
  "clusters": {
    "type": "array",
    "items": {
      "name": { "type": "string" },
      "items": { "type": "array", "items": { "type": "string" } }
    }
  }
}
Logic:
pythondef cluster_raw_thoughts(clusters):
    return {
        "clusters": [
            {
                "name": c["name"],
                "items": c["items"],
                "summary": f"{c['name']} related tasks",
                "relevance_score": len(c["items"])
            }
            for c in clusters
        ]
    }
```

---

## Tool 2: `identify_most_relevant_clusters`

**Description:**
```
Format the clusters the user selected as most relevant.
ChatGPT MUST ask the user which clusters matter most BEFORE calling this tool.
Input:
json{
  "selected_cluster_names": { "type": "array", "items": { "type": "string" } },
  "clusters": { "type": "array" }
}
Logic:
pythondef identify_most_relevant_clusters(selected_cluster_names, clusters):
    return {
        "top_clusters": [
            c for c in clusters 
            if c["name"] in selected_cluster_names
        ]
    }
```

---

## Tool 3: `specify_next_steps`

**Description:**
```
Generate next steps from the user's top clusters.
ChatGPT MUST have confirmed top clusters with user BEFORE calling this tool.
Input:
json{
  "top_clusters": { "type": "array" }
}
Logic:
pythondef specify_next_steps(top_clusters):
    steps = []
    for cluster in top_clusters[:3]:
        for item in cluster["items"][:2]:
            steps.append({
                "step": f"Work on: {item}",
                "source_cluster": cluster["name"],
                "effort": "low" if len(item) < 30 else "medium"
            })
    return {
        "next_steps": steps[:5],
        "clarity_summary": f"Focus on {', '.join(c['name'] for c in top_clusters[:3])}"
    }
```

---

## Keep:

- Business-only domain restriction in all tool descriptions
- Port 8002
- File structure
- Server Setup

## Remove:

- Tool registration for create_clarity_next_steps
- Mock output data
- Related tool logic

---