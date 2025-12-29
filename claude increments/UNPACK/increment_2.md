# Unpack — Increment 2 Briefing

## Question Clustering (No Solutions)

**Objective:** Implement `cluster_questions` tool and question collection flow via `assistant_guidance`.

**Philosophy:** Reveal where uncertainty concentrates — not where thinking is "stuck."

**Depends on:** Increment 1 (`formulate_problem`) complete and deployed.

**Produces:** Working tool in MCP Inspector + updated guidance for question collection.

---

## What This Increment Delivers

1. **Question collection flow** — LLM facilitates brainstorming via `assistant_guidance` (no new tool)
2. **`cluster_questions` tool** — Receives questions, returns semantic clusters by uncertainty type
3. **Summary markdown** — Pre-formatted export for Increment 3 widget

---

## Part 1: Question Collection Flow

This is NOT a tool. It's LLM behavior enforced via `assistant_guidance` after `formulate_problem` returns `confidence: high`.

### Updated `assistant_guidance` for `formulate_problem` (high confidence)

When `formulate_problem` returns high confidence, update the guidance to:

```python
guidance = {
    "action": "CONFIRM_AND_COLLECT_QUESTIONS",
    "instruction": """Present the problem statement to the user: '[full_statement]'
Ask: 'Does this capture what you're dealing with?'

Once confirmed, begin question brainstorming:

1. SEED with 3 starter questions relevant to this specific problem. Frame as: 
   'Here are a few questions to start with: [questions]. Now add yours.'

2. FACILITATE by offering LENSES, not answers:
   - 'What questions would [stakeholder] have about this?'
   - 'If you looked back in 6 months, what would you wish you'd asked?'
   - 'What if your assumption about [X] is wrong — what questions does that raise?'
   - 'What's underneath this — any questions about the root cause?'
   - 'What would need to be true for this to resolve well?'

3. COLLECT all questions (user's + any you seed). Track the count.

4. ENFORCE minimum: At least 3 user questions required before proceeding.

5. When user signals 'done', call cluster_questions with:
   - problem_statement: the confirmed full_statement
   - questions: array of ALL questions collected

RULES (non-negotiable):
- Do NOT discuss, evaluate, interpret, or answer any question
- Do NOT comment on importance, quality, or relevance
- Do NOT rephrase or combine user questions
- Do NOT say 'That's a good question' or 'This seems key'
- ONLY prompt for more questions or offer lenses
- The goal is QUANTITY and BREADTH, not depth

After cluster_questions is called, question collection is OVER. No new questions may be added.""",
    "problem_statement": full_statement,
}
```

---

## Part 2: `cluster_questions` Tool

### Tool Name
`cluster_questions`

### Tool Description

```
Validates clustered questions and generates summary for export.

WHEN TO CALL:
- User has confirmed their problem statement
- User has generated at least 3 questions
- User has signaled they are done brainstorming
- You have clustered the questions by uncertainty type

BEFORE CALLING:
1. Collect all questions from the brainstorming session
2. Group questions semantically into clusters by uncertainty type
3. Assign each cluster:
   - label: A short name describing what these questions are about
   - uncertainty_type: One of [causes, constraints, unknowns, dependencies, risks, options]
   - questions: The questions belonging to this cluster
4. Put questions that don't fit cleanly into "unclustered"

UNCERTAINTY TYPES:
- causes: Questions about WHY something happens
- constraints: Questions about what LIMITS options
- unknowns: Questions about MISSING INFORMATION
- dependencies: Questions about OTHER PEOPLE or factors
- risks: Questions about what could GO WRONG
- options: Questions about POSSIBLE PATHS forward

RULES:
- Minimum 3 questions total required
- Questions may remain unclustered if they don't fit any type
- Do NOT force questions into ill-fitting clusters
- Do NOT call if fewer than 3 questions collected
```

### Input Schema

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
          "label": {
            "type": "string",
            "description": "Short name describing what these questions are about"
          },
          "uncertainty_type": {
            "type": "string",
            "enum": ["causes", "constraints", "unknowns", "dependencies", "risks", "options"],
            "description": "Type of uncertainty these questions represent"
          },
          "questions": {
            "type": "array",
            "items": { "type": "string" },
            "minItems": 1,
            "description": "Questions belonging to this cluster"
          }
        },
        "required": ["label", "uncertainty_type", "questions"]
      },
      "description": "Questions grouped by uncertainty type (clustered by ChatGPT)"
    },
    "unclustered": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Questions that don't fit any uncertainty type cleanly",
      "default": []
    }
  },
  "required": ["problem_statement", "questions", "clusters"],
  "additionalProperties": false
}
```

**Note:** ChatGPT performs semantic clustering before calling the tool. The tool validates structure, generates insights, and creates the summary markdown.

### Output Schema

```json
{
  "clusters": [
    {
      "id": "cluster_1",
      "label": "string — emergent name for this cluster",
      "uncertainty_type": "causes | constraints | unknowns | dependencies | risks | options",
      "questions": ["string", "string"],
      "insight": "string — structural description of what this cluster represents"
    }
  ],
  "unclustered": ["string — questions that don't fit any cluster cleanly"],
  "summary_markdown": "string — pre-formatted Unpack Summary for export",
  "assistant_guidance": {
    "action": "PRESENT_CLUSTERS",
    "instruction": "string — how to present clusters to user"
  }
}
```

**Note:** `unclustered` is always present (may be empty array). Some questions genuinely don't fit a single uncertainty type — this is expected and must be surfaced, not hidden.

### Clustering Approach

**Pattern:** ChatGPT clusters → Tool validates and enriches.

ChatGPT performs semantic clustering before calling the tool. The tool:
1. Validates structure (minimum 3 questions, valid uncertainty types)
2. Generates insight per cluster
3. Generates `summary_markdown`
4. Returns `assistant_guidance` for presentation

**Why this approach:**
- ChatGPT is already an LLM — use it for semantic understanding
- Tool focuses on structure validation and output generation
- No extra API calls, no extra latency, no extra cost
- Clean separation: LLM understands, tool structures

---

## Tool Logic (`tool_logic.py`)

### Function: `cluster_questions`

```python
def cluster_questions(
    problem_statement: str,
    questions: list[str],
    clusters: list[dict],
    unclustered: list[str] | None = None,
) -> dict:
    """
    Validate clustered questions and generate summary.
    
    Args:
        problem_statement: Confirmed problem from formulate_problem
        questions: All questions collected
        clusters: ChatGPT-generated clusters with label, uncertainty_type, questions
        unclustered: Questions that don't fit any cluster (optional)
    
    Returns:
        Dict with validated clusters (with insights), summary_markdown, and guidance
    """
```

### Validation Rules

1. `problem_statement` must be non-empty
2. `questions` must have at least 3 items
3. Each cluster must have:
   - `label`: non-empty string
   - `uncertainty_type`: one of the 6 valid types
   - `questions`: at least 1 question
4. Invalid uncertainty types → map to "unknowns" as fallback
5. `unclustered` defaults to empty array if not provided

### Generate Insight per Cluster

For each cluster, generate a structural insight (not user-state interpretation):

```python
INSIGHT_TEMPLATES = {
    "causes": "These questions focus on what may be driving {topic}.",
    "constraints": "These questions explore what might be limiting options around {topic}.",
    "unknowns": "These questions identify missing information about {topic}.",
    "dependencies": "These questions consider how others factor into {topic}.",
    "risks": "These questions examine what could go wrong with {topic}.",
    "options": "These questions explore possible approaches to {topic}.",
}
```

Where `{topic}` is derived from the cluster label.

### Generate Summary Markdown

```python
def generate_summary_markdown(problem_statement: str, clusters: list[dict], unclustered: list[str]) -> str:
    lines = [
        "# Unpack Summary",
        "",
        "## Problem",
        problem_statement,
        "",
        "## Questions by Uncertainty Type",
        "",
    ]
    
    for cluster in clusters:
        lines.append(f"### {cluster['label']} ({cluster['uncertainty_type']})")
        for q in cluster["questions"]:
            lines.append(f"- {q}")
        lines.append(f"_{cluster['insight']}_")
        lines.append("")
    
    if unclustered:
        lines.append("### Unclustered")
        for q in unclustered:
            lines.append(f"- {q}")
        lines.append("_These questions don't fit a single uncertainty type._")
        lines.append("")
    
    lines.extend([
        "---",
        "Generated with Unpack • fulfilling-productivity.com"
    ])
    
    return "\n".join(lines)
```

---

## Tool Handler (`tools/cluster_questions.py`)

### Response Structure

```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text=f"Clustered {len(questions)} questions into {len(clusters)} groups."
    )],
    structuredContent={
        "clusters": clusters_with_insights,
        "unclustered": unclustered_questions,  # May be empty, but always present
        "summary_markdown": summary_md,
        "assistant_guidance": {
            "action": "PRESENT_CLUSTERS",
            "instruction": (
                "Present the clusters to the user. For each cluster, show:\n"
                "- The cluster name\n"
                "- The uncertainty type\n"
                "- The questions in that cluster\n"
                "- The insight\n\n"
                "If there are unclustered questions, show them separately.\n\n"
                "Then ask: 'Which area would you like to explore further?'\n\n"
                "Do NOT offer advice or solutions. Do NOT answer any questions.\n"
                "Wait for the user to select a cluster."
            ),
        },
    },
)
```

### Error Handling

Return structured errors. Let the LLM phrase the message.

**Fewer than 3 questions:**
```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text="Insufficient questions for clustering."
    )],
    structuredContent={
        "error_type": "insufficient_questions",
        "count": len(questions),
        "required_minimum": 3,
        "assistant_guidance": {
            "action": "REQUEST_MORE_QUESTIONS",
            "instruction": "Tell the user you need at least 3 questions to find patterns. Ask what other questions come to mind."
        }
    },
    isError=True,
)
```

**Empty problem statement:**
```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text="Missing problem statement."
    )],
    structuredContent={
        "error_type": "missing_problem_statement",
        "assistant_guidance": {
            "action": "RESTART_FLOW",
            "instruction": "The problem statement is missing. Ask the user to describe their problem first."
        }
    },
    isError=True,
)
```

**Invalid cluster structure:**
```python
return mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text="Invalid cluster structure."
    )],
    structuredContent={
        "error_type": "invalid_clusters",
        "assistant_guidance": {
            "action": "RETRY_CLUSTERING",
            "instruction": "Re-cluster the questions ensuring each cluster has a label, uncertainty_type, and at least one question."
        }
    },
    isError=True,
)
```

---

## File Structure

```
apps/unpack/
├── config.py                  # No changes needed
├── tool_logic.py              # Add cluster_questions function
├── tools/
│   ├── __init__.py            # Import cluster_questions
│   ├── base.py                # Unchanged
│   ├── formulate_problem.py   # Update assistant_guidance for high confidence
│   └── cluster_questions.py   # NEW FILE
└── tests/
    ├── test_formulate_problem.py
    └── test_cluster_questions.py  # NEW FILE
```

No new dependencies required.

---

## Unit Test Requirements

Test file: `apps/unpack/tests/test_cluster_questions.py`

### Test Cases

**1. Valid input with clusters:**
```python
Input: {
    "problem_statement": "I am trying to get respect at work...",
    "questions": [
        "Why does the team interrupt me?",
        "Should I talk to my manager?",
        "What if it gets worse?",
        "Is this intentional?"
    ],
    "clusters": [
        {"label": "Root cause", "uncertainty_type": "causes", "questions": ["Why does the team interrupt me?", "Is this intentional?"]},
        {"label": "Response options", "uncertainty_type": "options", "questions": ["Should I talk to my manager?"]},
        {"label": "Potential risks", "uncertainty_type": "risks", "questions": ["What if it gets worse?"]}
    ],
    "unclustered": []
}

Expected: 
- Returns clusters with insights added
- Each cluster has valid uncertainty_type
- summary_markdown is well-formed
- assistant_guidance has action: "PRESENT_CLUSTERS"
```

**2. Fewer than 3 questions:**
```python
Input: {
    "problem_statement": "...",
    "questions": ["Why?", "What?"],
    "clusters": [...]
}

Expected: 
- isError: true
- error_type: "insufficient_questions"
- count: 2
- required_minimum: 3
```

**3. Empty problem statement:**
```python
Input: {
    "problem_statement": "",
    "questions": ["Q1", "Q2", "Q3"],
    "clusters": [...]
}

Expected:
- isError: true
- error_type: "missing_problem_statement"
```

**4. With unclustered questions:**
```python
Input: {
    "problem_statement": "...",
    "questions": ["Why?", "What's for lunch?", "Should I?"],
    "clusters": [
        {"label": "Causes", "uncertainty_type": "causes", "questions": ["Why?"]},
        {"label": "Options", "uncertainty_type": "options", "questions": ["Should I?"]}
    ],
    "unclustered": ["What's for lunch?"]
}

Expected:
- unclustered array preserved in output
- summary_markdown includes "Unclustered" section
```

**5. Invalid uncertainty type:**
```python
Input: {
    "clusters": [
        {"label": "Test", "uncertainty_type": "invalid_type", "questions": ["Q1"]}
    ]
}

Expected:
- Maps to "unknowns" as fallback
- Does not reject
```

**6. Summary markdown format:**
```python
Expected:
- Starts with "# Unpack Summary"
- Contains "## Problem"
- Contains "## Questions by Uncertainty Type"
- Each cluster has heading with label and type
- Insights use structural language (not "You're uncertain...")
- Unclustered section present if applicable
- Ends with attribution line
```

### Test Assertions

For each successful test:
- Response contains `content` array with text
- Response contains `structuredContent` with required fields
- `clusters` array has insights added to each cluster
- `unclustered` array exists (may be empty)
- `summary_markdown` is non-empty string
- `assistant_guidance.action` is "PRESENT_CLUSTERS"
- `assistant_guidance.instruction` contains "Do NOT offer advice"
- Insight text uses structural framing ("These questions focus on...") not user-state framing ("You're uncertain...")

---

## Integration Notes

### Increment 3 Dependency

The widget (Increment 3) will:
1. Receive `clusters` from this tool's output
2. Display them visually
3. Let user select one cluster
4. Include "Copy Summary" button using `summary_markdown`

This increment prepares all data the widget needs.

### State Transition

```
formulate_problem (confidence: high)
    ↓
assistant_guidance: CONFIRM_AND_COLLECT_QUESTIONS
    ↓
[LLM facilitates question brainstorming in chat]
    ↓
User: "done"
    ↓
cluster_questions
    ↓
assistant_guidance: PRESENT_CLUSTERS
    ↓
[Increment 3: Widget displays clusters]
```

---

## Update to `formulate_problem.py`

When confidence is high, update the guidance:

```python
if not needs_clarification:
    guidance = {
        "action": "CONFIRM_AND_COLLECT_QUESTIONS",
        "instruction": """Present the problem statement: '{full_statement}'
Ask: 'Does this capture what you're dealing with?'

Once confirmed, facilitate question brainstorming:

1. SEED with 3 starter questions relevant to this problem:
   - A 'why' question about causes
   - A 'what if' question about risks
   - A 'who' question about stakeholders
   Frame as: 'Here are a few to start. Now add yours.'

2. FACILITATE by offering LENSES (not answers):
   - 'What questions would [stakeholder] have?'
   - 'Looking back in 6 months, what would you wish you'd asked?'
   - 'What if your assumption about [X] is wrong?'
   - 'What's underneath this — questions about root cause?'
   - 'What would need to be true for this to resolve?'

3. COLLECT all questions. Track count. Minimum 3 from user.

4. When user says 'done', cluster the questions by uncertainty type and call cluster_questions.

RULES:
- Do NOT discuss, evaluate, or answer any question
- Do NOT comment on importance or quality
- Do NOT rephrase user questions
- ONLY prompt for more or offer lenses
- Goal is QUANTITY and BREADTH

After cluster_questions is called, collection is OVER.""",
        "problem_statement": full_statement,
    }
```

---

## Acceptance Criteria

- [ ] `cluster_questions` tool registered and appears in tool list
- [ ] Tool accepts `problem_statement`, `questions`, `clusters`, and optional `unclustered`
- [ ] Tool validates minimum 3 questions
- [ ] Tool validates cluster structure (label, uncertainty_type, questions)
- [ ] Invalid uncertainty types mapped to "unknowns" (not rejected)
- [ ] Unclustered questions are preserved and surfaced
- [ ] Each cluster gets a structural insight sentence (not user-state interpretation)
- [ ] `summary_markdown` follows specified format including unclustered section
- [ ] Errors return structured data, not conversational messages
- [ ] `assistant_guidance` instructs LLM to present without advice
- [ ] `formulate_problem` guidance updated for question collection
- [ ] All unit tests pass
- [ ] MCP Inspector validates tool response structure

---

## MCP Inspector Validation

After implementation:

1. Start server locally
2. Connect MCP Inspector to `http://localhost:8003/mcp`
3. Call `formulate_problem` with high-confidence input
4. Verify updated `assistant_guidance` for question collection
5. Call `cluster_questions` with test data
6. Verify response structure matches schema
7. Verify `summary_markdown` is well-formed

---

## Deployment

After tests pass:
1. Commit to `fulfilling-productivity` repo
2. Push to GitHub
3. Render auto-deploys
4. Test via `https://unpack.fulfilling-productivity.com/mcp`

### Environment Variables (Render)

No new environment variables required for this increment.

| Variable | Required | Description |
|----------|----------|-------------|
| `ENV` | Yes | `production` |
| `CORS_ALLOWED_ORIGINS` | Yes | `https://web-sandbox.oaiusercontent.com,https://chatgpt.com` |
| `LOG_LEVEL` | No | `INFO` (default) |