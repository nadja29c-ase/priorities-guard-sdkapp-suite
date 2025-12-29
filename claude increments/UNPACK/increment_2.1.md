# Unpack — Increment 2.1 Briefing

## Simplify Clustering: Semantic Similarity with Emergent Themes

**Objective:** Replace pre-defined uncertainty types with emergent semantic clustering.

**Depends on:** Increment 2 complete.

**Scope:** Refactor only — no new tools, no new files.

---

## What This Increment Changes

| Before (Increment 2) | After (Increment 2.1) |
|----------------------|----------------------|
| 6 fixed uncertainty types | No fixed types |
| `uncertainty_type` field required | Removed |
| `label` field | Renamed to `theme` |
| Type-specific insight templates | Single generic insight |
| ChatGPT assigns to categories | ChatGPT groups by meaning |

---

## Why This Change

The original approach forced questions into pre-defined buckets:
- causes, constraints, unknowns, dependencies, risks, options

This is:
- Prescriptive (contradicts facilitator stance)
- Artificial (questions don't naturally fit 6 types)
- Over-engineered

**New approach:** Let clusters emerge from semantic similarity. ChatGPT names the themes.

---

## Updated Tool Description

```
Validates clustered questions and generates summary for export.

WHEN TO CALL:
- User has confirmed their problem statement
- User has generated at least 3 questions
- User has signaled they are done brainstorming
- You have clustered the questions by semantic similarity

BEFORE CALLING:
1. Group questions by semantic similarity — what do they have in common?
2. Name each cluster with a short THEME that captures the shared meaning
3. Questions that don't fit any group go in "unclustered"

RULES:
- Themes should be descriptive, not generic ("Understanding the behavior" not "Questions")
- Do NOT use pre-defined categories — let themes emerge from the questions
- A cluster needs at least 2 questions (single questions go to unclustered)
- Minimum 3 questions total required
- Do NOT call if fewer than 3 questions collected
```

---

## Updated Input Schema

```json
{
  "type": "object",
  "properties": {
    "problem_statement": {
      "type": "string",
      "description": "The confirmed problem statement from formulate_problem"
    },
    "questions": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 3,
      "description": "All questions collected during brainstorming"
    },
    "clusters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "theme": {
            "type": "string",
            "description": "Short theme capturing what these questions have in common"
          },
          "questions": {
            "type": "array",
            "items": { "type": "string" },
            "minItems": 1,
            "description": "Questions belonging to this cluster"
          }
        },
        "required": ["theme", "questions"]
      },
      "description": "Questions grouped by semantic similarity"
    },
    "unclustered": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Questions that don't fit any cluster",
      "default": []
    }
  },
  "required": ["problem_statement", "questions", "clusters"],
  "additionalProperties": false
}
```

**Changes:**
- Removed `uncertainty_type` from cluster items
- Renamed `label` → `theme`

---

## Updated Output Schema

```json
{
  "clusters": [
    {
      "id": "cluster_1",
      "theme": "string — emergent theme for this cluster",
      "questions": ["string", "string"],
      "insight": "string — structural description"
    }
  ],
  "unclustered": ["string"],
  "summary_markdown": "string",
  "assistant_guidance": {
    "action": "PRESENT_CLUSTERS",
    "instruction": "string"
  }
}
```

**Changes:**
- Removed `uncertainty_type` from output
- Renamed `label` → `theme`

---

## Code Changes

### `tool_logic.py`

**Remove:**
```python
VALID_UNCERTAINTY_TYPES = frozenset([
    "causes",
    "constraints",
    "unknowns",
    "dependencies",
    "risks",
    "options",
])

INSIGHT_TEMPLATES = {
    "causes": "These questions focus on what may be driving {topic}.",
    "constraints": "These questions explore what might be limiting options around {topic}.",
    "unknowns": "These questions identify missing information about {topic}.",
    "dependencies": "These questions consider how others factor into {topic}.",
    "risks": "These questions examine what could go wrong with {topic}.",
    "options": "These questions explore possible approaches to {topic}.",
}
```

**Replace `generate_insight` with:**
```python
def generate_insight(theme: str) -> str:
    """Generate a structural insight for a cluster."""
    return f"These questions explore {theme.lower()}."
```

**Update `cluster_questions` function:**
- Remove `uncertainty_type` validation
- Change `label` → `theme` throughout
- Remove mapping of invalid types to "unknowns"

**Update `generate_summary_markdown`:**
```python
def generate_summary_markdown(
    problem_statement: str,
    clusters: list[dict],
    unclustered: list[str],
) -> str:
    """Generate markdown summary for export."""
    lines = [
        "# Unpack Summary",
        "",
        "## Problem",
        problem_statement,
        "",
        "## Questions by Theme",
        "",
    ]

    for cluster in clusters:
        lines.append(f"### {cluster['theme']}")
        for q in cluster["questions"]:
            lines.append(f"- {q}")
        lines.append(f"_{cluster['insight']}_")
        lines.append("")

    if unclustered:
        lines.append("### Other Questions")
        for q in unclustered:
            lines.append(f"- {q}")
        lines.append("_These questions didn't fit a clear theme._")
        lines.append("")

    lines.extend([
        "---",
        "Generated with Unpack • fulfilling-productivity.com"
    ])

    return "\n".join(lines)
```

**Changes:**
- "Questions by Uncertainty Type" → "Questions by Theme"
- `{cluster['label']} ({cluster['uncertainty_type']})` → `{cluster['theme']}`
- "Unclustered" → "Other Questions"
- Updated unclustered insight text

---

### `tools/cluster_questions.py`

**Update Pydantic models:**

```python
class ClusterItem(BaseModel):
    """A single cluster of semantically similar questions."""
    theme: str = Field(..., description="Theme capturing what these questions have in common")
    questions: list[str] = Field(..., min_length=1, description="Questions in this cluster")


class ClusterQuestionsInput(BaseModel):
    """Input for cluster_questions tool."""
    problem_statement: str = Field(..., description="Confirmed problem statement")
    questions: list[str] = Field(..., min_length=3, description="All questions collected")
    clusters: list[ClusterItem] = Field(..., description="Questions grouped by semantic similarity")
    unclustered: list[str] = Field(default_factory=list, description="Questions that don't fit any cluster")
```

**Update INPUT_SCHEMA:**
- Remove `uncertainty_type` from cluster properties
- Rename `label` → `theme`

**Update DESCRIPTION:**
- Replace with new tool description (see above)

---

### `tests/test_cluster_questions.py`

**Update test data:**

```python
# Before
{
    "clusters": [
        {"label": "Root cause", "uncertainty_type": "causes", "questions": ["Why?"]}
    ]
}

# After
{
    "clusters": [
        {"theme": "Understanding the root cause", "questions": ["Why?", "What's causing this?"]}
    ]
}
```

**Remove tests for:**
- Invalid uncertainty type mapping
- Uncertainty type validation

**Add tests for:**
- Theme is non-empty string
- Cluster with only 1 question (should warn or move to unclustered)

---

## Updated `assistant_guidance` in `formulate_problem.py`

Change the clustering instruction:

```python
"4. When user says 'done', group questions by semantic similarity, 
    name each group with a descriptive theme, and call cluster_questions."
```

Remove any reference to "uncertainty types."

---

## Example: Before vs After

**Questions collected:**
- "Why does the team interrupt me?"
- "Is this intentional?"
- "Should I talk to my manager?"
- "Should I address it directly?"
- "What if it gets worse?"
- "Could this hurt my career?"

**Before (Increment 2):**
```json
{
  "clusters": [
    {"label": "Root cause", "uncertainty_type": "causes", "questions": ["Why does the team interrupt me?", "Is this intentional?"]},
    {"label": "Response options", "uncertainty_type": "options", "questions": ["Should I talk to my manager?", "Should I address it directly?"]},
    {"label": "Potential risks", "uncertainty_type": "risks", "questions": ["What if it gets worse?", "Could this hurt my career?"]}
  ]
}
```

**After (Increment 2.1):**
```json
{
  "clusters": [
    {"theme": "Understanding the behavior", "questions": ["Why does the team interrupt me?", "Is this intentional?"]},
    {"theme": "How to respond", "questions": ["Should I talk to my manager?", "Should I address it directly?"]},
    {"theme": "Potential consequences", "questions": ["What if it gets worse?", "Could this hurt my career?"]}
  ]
}
```

Same groupings, but themes emerge from meaning — not forced into pre-defined categories.

---

## Acceptance Criteria

- [ ] `uncertainty_type` removed from input schema
- [ ] `uncertainty_type` removed from output schema
- [ ] `label` renamed to `theme` throughout
- [ ] `VALID_UNCERTAINTY_TYPES` constant removed
- [ ] `INSIGHT_TEMPLATES` dict removed
- [ ] `generate_insight()` simplified to single template
- [ ] `generate_summary_markdown()` updated for themes
- [ ] Tool description updated (no pre-defined categories)
- [ ] `formulate_problem` guidance updated (no uncertainty types)
- [ ] All tests updated and passing
- [ ] MCP Inspector validates new schema

---

## Files to Modify

| File | Changes |
|------|---------|
| `tool_logic.py` | Remove constants, simplify insight, rename label→theme |
| `tools/cluster_questions.py` | Update schema, models, description |
| `tools/formulate_problem.py` | Update guidance (remove uncertainty type reference) |
| `tests/test_cluster_questions.py` | Update test data, remove type validation tests |

---

## Deployment

After tests pass:
1. Commit to `fulfilling-productivity` repo
2. Push to GitHub
3. Render auto-deploys
4. Test via MCP Inspector with new schema
