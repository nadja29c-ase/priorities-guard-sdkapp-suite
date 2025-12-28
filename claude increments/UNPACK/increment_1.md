# Unpack — Increment 1 Briefing

**Increment:** 1 of 4  
**Scope:** MCP Server Foundation + `formulate_problem` Tool  
**Prerequisites:** 
1. Read `unpack-north-star.md` first (context)
2. Read `unpack-compliance-requirements.md` (mandatory rules)

**Output:** Working `formulate_problem` tool validated in MCP Inspector

---

## Reuse from Clarity (IMPORTANT)

Before writing new code, examine Clarity's implementation in the repository. **Replicate these patterns** (copy and adapt, do not import):

### File Locations in Priority Guardian Repo

```
priority-guardian/
├── mcp_server/
│   └── clarity/                    # ← STUDY THIS
│       ├── server.py               # FastMCP server setup, CORS, middleware
│       ├── config.py               # Environment config pattern
│       ├── tool_logic.py           # Pure business logic (no MCP types)
│       ├── handlers/
│       │   ├── resources.py        # Widget registration pattern
│       │   └── tools.py            # Tool dispatcher with auth + timing
│       └── tools/
│           ├── __init__.py         # Tool registry pattern
│           ├── base.py             # ToolDefinition dataclass
│           └── organize_thoughts.py # Complete tool example
└── tests/unit/mcp_clarity/
    └── test_tool_logic.py          # Test patterns
```

### Patterns to Copy

**1. Server Setup (`server.py`):**
- FastMCP initialization with `stateless_http=True`
- CORS middleware configuration
- Health endpoint pattern

**2. Tool Registry (`tools/__init__.py` + `tools/base.py`):**
```python
# base.py - ToolDefinition dataclass
@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict
    required_scopes: list[str]
    widget_uri: str | None
    handle: Callable[[str, str, dict], Awaitable[Any]]
    read_only_hint: bool = True
    destructive_hint: bool = False
    open_world_hint: bool = False

# __init__.py - Registry pattern
TOOL_REGISTRY: dict[str, ToolDefinition] = {}

def register_tool(tool: ToolDefinition) -> None:
    TOOL_REGISTRY[tool.name] = tool
```

**3. Tool Implementation (`tools/organize_thoughts.py`):**
- DESCRIPTION constant with WHEN/WHEN NOT to call
- INPUT_SCHEMA as JSON Schema dict
- Pydantic models for input validation
- Handler signature: `async def handle(user_id, correlation_id, arguments) -> CallToolResult`
- Self-registration at import: `register_tool(ToolDefinition(...))`

**4. Response Format:**
```python
return mcp_types.CallToolResult(
    content=[
        mcp_types.TextContent(type="text", text="Summary for model")
    ],
    structuredContent={
        "data": {...},
        "assistant_guidance": "Instructions for LLM..."
    },
    _meta={
        "openai/outputTemplate": WIDGET_URI,  # Only if widget
        "openai/toolInvocation/invoking": "Processing...",
        "openai/toolInvocation/invoked": "Done."
    }
)
```

**5. Test Patterns (`tests/unit/mcp_clarity/test_tool_logic.py`):**
- Pydantic model validation tests
- Pure function output tests  
- Tool boundary tests (mocked auth via `patch`)
- Output schema stability tests
- Ordering guarantee tests

### Key Differences for Unpack

| Clarity | Unpack |
|---------|--------|
| OAuth required (`clarity.write` scope) | No auth (`noauth`) |
| Persistence (save/load boards) | Session-only (no DB) |
| Multiple tools (7) | Two tools |
| Complex widget (React) | Simpler widget |

**Simplifications for Unpack:**
- Skip `mcp_auth.py` (no JWT validation)
- Skip `persistence.py` (no DB)
- Skip `http_client.py` (no backend calls)
- Handler receives empty `user_id` (no auth)

### Isolation Reminder

Copy patterns into `unpack/` folder. Do NOT import from `mcp_server/clarity/`.

**Why this matters:** Clarity's patterns are debugged and SDK-compliant. Copying them saves debugging time and ensures compliance.

---

## Objective

Set up the MCP server and implement the first tool (`formulate_problem`) that transforms vague problem descriptions into structured problem statements.

---

## Deliverables

1. Project structure (FastMCP Python server)
2. MCP server entry point with health check
3. `formulate_problem` tool with complete schema
4. Unit tests for tool logic
5. Local validation via MCP Inspector

---

## Project Structure

```
priority-guardian/
└── mcp_server/
    └── unpack/                     # New - isolated from clarity/
        ├── __init__.py
        ├── server.py               # FastMCP server entry (copy from clarity)
        ├── config.py               # Environment config
        ├── tool_logic.py           # Pure business logic
        ├── handlers/
        │   ├── __init__.py
        │   └── tools.py            # Tool dispatcher (simplified - no auth)
        ├── tools/
        │   ├── __init__.py         # Registry + list_tools
        │   ├── base.py             # ToolDefinition dataclass
        │   └── formulate_problem.py
        └── tests/
            ├── __init__.py
            └── test_formulate_problem.py
```

**Note:** 
- Widget folder is NOT part of this increment
- No `mcp_auth.py` (Unpack uses `noauth`)
- No `persistence.py` (session-only, no DB)
- No `http_client.py` (no backend calls)

---

## Tool Specification: `formulate_problem`

### Purpose

Transform a vague problem description into a structured statement following this format:

> "[Actor] is trying to [goal], but [obstacle] keeps happening, which costs [cost]."

### Input Schema

```json
{
  "type": "object",
  "properties": {
    "raw_problem": {
      "type": "string",
      "description": "The user's initial, unstructured problem description"
    }
  },
  "required": ["raw_problem"],
  "additionalProperties": false
}
```

### Output Schema

```json
{
  "type": "object",
  "properties": {
    "formulated_problem": {
      "type": "object",
      "properties": {
        "actor": { "type": "string" },
        "goal": { "type": "string" },
        "obstacle": { "type": "string" },
        "cost": { "type": "string" },
        "full_statement": { "type": "string" }
      },
      "required": ["actor", "goal", "obstacle", "cost", "full_statement"]
    },
    "confidence": {
      "type": "string",
      "enum": ["high", "medium", "low"]
    },
    "clarifying_question": {
      "type": "string"
    }
  },
  "required": ["formulated_problem", "confidence"]
}
```

### Tool Description

This description controls WHEN ChatGPT calls the tool. Be precise.

```
Transforms a vague problem description into a structured problem statement.

Call this tool when:
- User describes a problem, challenge, or stuck situation
- User says they need help thinking through something
- User mentions feeling overwhelmed or unclear

Do NOT call this tool when:
- User is asking general questions unrelated to a personal problem
- User has already confirmed their problem statement in this session
- User is listing questions (that's a later step)

Output format: "[Actor] is trying to [goal], but [obstacle] keeps happening, which costs [cost]."
```

### Tool Annotations

```json
{
  "readOnlyHint": true,
  "openWorldHint": false,
  "destructiveHint": false
}
```

### Security Schemes

```json
{
  "securitySchemes": [{ "type": "noauth" }]
}
```

**Note:** Unlike Clarity which requires OAuth (`clarity.write` scope), Unpack has no authentication. The tool dispatcher should skip auth validation entirely.

**Simplified Dispatcher Pattern (no auth):**
```python
async def call_tool_request(req: mcp_types.CallToolRequest) -> mcp_types.CallToolResult:
    """Handle tool calls - no auth required for Unpack."""
    name = req.params.name
    arguments = req.params.arguments or {}
    
    tool = get_tool(name)
    if tool is None:
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text=f"Unknown tool: {name}")],
            isError=True,
        )
    
    # No auth - pass empty user_id
    try:
        result = await tool.handle("", "", arguments)
    except Exception:
        logger.exception("tool.dispatch.error", tool_name=name)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Something went wrong.")],
            isError=True,
        )
    
    return result
```

### Response Format

The tool must return both `content` and `structuredContent`.

**IMPORTANT:** This tool MUST NOT include `_meta.openai/outputTemplate`. Unpack tools do not render widgets directly.

```python
return {
    "content": [
        {
            "type": "text",
            "text": f"Formulated problem: {full_statement}"
        }
    ],
    "structuredContent": {
        "formulated_problem": {
            "actor": actor,
            "goal": goal,
            "obstacle": obstacle,
            "cost": cost,
            "full_statement": full_statement
        },
        "confidence": confidence,
        "clarifying_question": clarifying_question,  # Optional, include only if confidence != "high"
        "assistant_guidance": "Present the formulated problem statement to the user and invite confirmation or correction. Use this framing: 'Here's what I'm hearing: [full_statement]. Does this capture it, or should we adjust anything?' If confidence is medium or low, also ask the clarifying_question. Do not offer advice or solutions. Wait for the user's response before continuing."
    }
}
```

---

## Implementation Notes

### Parsing Logic

The tool needs to extract four components from raw input:
- **Actor:** Who is experiencing the problem (default to "I" if unclear)
- **Goal:** What they're trying to achieve
- **Obstacle:** What keeps blocking progress
- **Cost:** Impact in terms of time, money, energy, or clarity

**Approach for v1:**

Start with pattern matching + heuristics. Look for keywords like "trying to", "but", "because", "keeps happening".

⚠️ **Technical debt note:** Pattern matching is acceptable for v1 because the user confirms/corrects the formulation. However, this is temporary. Before scaling, replace with internal LLM extraction (small constrained prompt, deterministic schema output). The formulation quality is foundational to user trust.

### Handling Non-Problem Input

If input doesn't appear to be a personal problem (e.g., "What's the weather like?"):
- Treat it as **unclear context**, not user error
- Do NOT moralize or explain what the app is for
- Do NOT say "This app is designed for..."
- Simply return low confidence with a neutral clarifying question
- Let the LLM handle redirection naturally via `assistant_guidance`

### Confidence Scoring

| Confidence | Condition |
|------------|-----------|
| `high` | All 4 components clearly identified |
| `medium` | 2-3 components clear, 1-2 inferred |
| `low` | Significant guessing required |

### Clarifying Questions

Generate based on what's missing:
- Missing goal: "What are you ultimately trying to achieve?"
- Missing obstacle: "What specifically keeps getting in the way?"
- Missing cost: "What is this costing you — time, money, energy, peace of mind?"

---

## Unit Test Requirements

Test file: `server/tests/test_formulate_problem.py`

### Test Cases

**1. Clear input with all components:**
```
Input: "I'm trying to grow my freelance business but I keep taking low-paying projects because I'm scared to say no, and it's costing me time and energy."

Expected: confidence = "high", all components extracted
```

**2. Vague input:**
```
Input: "I'm stressed about work."

Expected: confidence = "low", clarifying_question present
```

**3. Missing cost:**
```
Input: "I want to get promoted but my manager doesn't notice my work."

Expected: confidence = "medium", cost inferred or clarifying_question asks about cost
```

**4. Very long input:**
```
Input: [200+ word rambling description]

Expected: Tool extracts core components, doesn't fail
```

**5. Non-problem input:**
```
Input: "What's the weather like?"

Expected: Tool handles gracefully (low confidence, generic clarifying question)
```

**6. Empty input:**
```
Input: ""

Expected: Tool returns structured error with guidance
```

### Error Response Pattern

When input is invalid or empty, return structured error info:

```python
return {
    "content": [
        {
            "type": "text",
            "text": "Unable to formulate problem: no input provided"
        }
    ],
    "structuredContent": {
        "error_type": "invalid_input",
        "error_reason": "empty_input",
        "assistant_guidance": "Ask the user to describe a challenge or situation they're trying to think through. Keep it warm and inviting, not instructional."
    }
}
```

### Test Assertions

For each test:
- Response contains `content` array with text
- Response contains `structuredContent` with required fields
- `formulated_problem` has all 5 required fields
- `confidence` is one of: "high", "medium", "low"
- `assistant_guidance` is present and non-empty
- If confidence != "high", `clarifying_question` is present

---

## MCP Inspector Validation

After implementation, validate with MCP Inspector:

1. Start server locally
2. Connect MCP Inspector to `http://localhost:<port>/mcp`
3. List tools — verify `formulate_problem` appears with correct description
4. Call tool with test inputs
5. Verify response structure matches schema
6. Verify `structuredContent` contains `assistant_guidance`

### Validation Checklist

- [ ] Tool appears in tool list
- [ ] Tool description matches spec
- [ ] Input schema validated (rejects invalid input)
- [ ] Output contains both `content` and `structuredContent`
- [ ] `structuredContent.formulated_problem` has all required fields
- [ ] `structuredContent.assistant_guidance` is present
- [ ] Response time < 2 seconds

---

## Dependencies

```
# requirements.txt
fastmcp>=0.1.0
pydantic>=2.0.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
```

---

## What This Increment Does NOT Include

- `cluster_questions` tool (Increment 2)
- Widget (Increment 3)
- Integration testing (Increment 4)
- Deployment configuration (Increment 4)
- Production hosting setup (Increment 4)

---

## Done Criteria

Increment 1 is complete when:

1. [ ] Server starts without errors
2. [ ] `formulate_problem` tool registered and discoverable
3. [ ] Tool returns valid response for all test cases
4. [ ] Unit tests pass
5. [ ] MCP Inspector validation checklist complete
6. [ ] No hardcoded values that would break in production

**Compliance verification (from `unpack-compliance-requirements.md`):**
7. [ ] Tool has all three annotations: `readOnlyHint: true`, `destructiveHint: false`, `openWorldHint: false`
8. [ ] Tool name is human-readable verb (`formulate_problem`)
9. [ ] Tool description accurately explains behavior, starts with action
10. [ ] Tool input is minimal (only `raw_problem` field)
11. [ ] All async operations wrapped in try/catch
12. [ ] Error responses are human-readable (no stack traces)

---

## Next Increment

After Increment 1 is validated, proceed to **Increment 2: `cluster_questions` Tool**.