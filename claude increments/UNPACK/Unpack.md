# Unpack — North Star Context

**Status:** Pre-development  
**Target:** ChatGPT Apps SDK submission  
**Timeline:** 4-5 days to submission-ready

---

## Repository Strategy

Unpack will be built inside the Priority Guardian repository to maximize code pattern reuse, then extracted to a separate repo later.

**Isolation Rule:** Unpack must be fully self-contained within its folder. No imports from other Priority Guardian modules (`backend/`, `clarity/`, `focused/`). If utility code is needed, copy it into Unpack's folder. This enables clean extraction to a separate repo later.

```
priority-guardian/
├── backend/              # Shared backend (Focused, Clarity, Done) — DO NOT IMPORT
├── clarity/              # Clarity MCP + widget — DO NOT IMPORT
├── focused/              # Focused MCP + widget — DO NOT IMPORT
└── unpack/               # ISOLATED — fully self-contained
    ├── server/
    │   ├── main.py
    │   ├── tools/
    │   └── tests/
    ├── widget/
    ├── requirements.txt  # Own dependencies
    └── README.md
```

**What IS allowed:** Look at Clarity's patterns (widget structure, FastMCP setup, error handling) and replicate them.

**What is NOT allowed:** `from backend.utils import ...` or `from clarity.widgets import ...`

---

## What Unpack Is

A question-first sensemaking tool that helps people discover **where to think next**, not what to do.

**Core insight:** Questions unlock answers. Most people jump to solutions before understanding what they're actually solving. Unpack slows that down.

**What it is NOT:**
- Not a coach
- Not an advisor
- Not a decision-maker
- Not therapy

**Role:** Pure facilitator. The LLM guides the process but never prescribes.

---

## Target User

**Anyone stuck on a problem.**

Examples:
- Freelancer unsure whether to raise rates
- Manager deciding whether to have a difficult conversation
- Founder choosing between competing priorities
- Employee weighing a job change

**Use frequency:** Occasional (when stuck), not daily.

**Session length:** 5-10 minutes, single session, no persistence needed.

---

## Problem It Solves

| User State Before | User State After |
|-------------------|------------------|
| Vague sense of being stuck | Concrete problem statement |
| Scattered thoughts | Organized questions |
| "I don't know where to start" | "I know where clarity is missing" |
| Tempted to jump to solutions | Grounded in what's actually unknown |

**The output is not an answer. It's orientation.**

---

## User Flow (4 Steps)

```
Step 1: Describe Problem
        User dumps unstructured problem description
        ↓
        Tool: formulate_problem
        ↓
        LLM presents structured statement, user confirms

Step 2: Generate Questions
        User lists ALL questions they'd want answered
        ↓
        LLM collects questions
        ↓
        Stopping rules:
        - Minimum: 3 questions required
        - If < 5 questions: LLM prompts ONCE for more
        - After one prompt, accept "done" regardless
        - Never challenge user's "done" twice
        ↓
        User signals "done"

Step 3: Cluster Questions
        Tool: cluster_questions
        ↓
        Widget displays clusters by uncertainty type
        ↓
        User selects one cluster to explore

Step 4: Closing Reflection
        LLM reflects on what the chosen cluster reveals
        ↓
        One non-prescriptive observation
        ↓
        One reflection QUESTION (not a next step, not advice)
        ↓
        End — no iteration, no looping back
```

---

## MCP Tools

### Tool 1: `formulate_problem`

**Purpose:** Validate and format problem components that ChatGPT has already extracted from user input.

**Pattern:** LLM extracts → Tool validates/formats (same as Clarity's `organize_thoughts`)

**Input:** Structured components extracted by ChatGPT
```json
{
  "actor": "string",
  "goal": "string", 
  "obstacle": "string",
  "cost": "string"
}
```

**Output:**
- `full_statement`: "[Actor] is trying to [goal], but [obstacle] keeps happening, which costs [cost]."
- `confidence`: high | medium | low (based on component quality)
- `clarifying_question`: Present if any component is weak/empty

**Tool responsibilities:**
- Validate all 4 components present and non-empty
- Construct `full_statement` from components
- Determine `confidence` (empty/vague components = lower confidence)
- Generate `clarifying_question` if confidence not high
- Return `assistant_guidance` for LLM behavior

**Triggers when:** User describes a problem, challenge, or stuck situation. ChatGPT extracts the 4 components and passes them to the tool.

**Does NOT:** Parse raw text (ChatGPT does that), advise, solve, or suggest.

---

### Tool 2: `cluster_questions`

**Purpose:** Organize questions into clusters by type of uncertainty.

**Input:** 
- Confirmed problem statement
- Array of user questions (3+ required)

**Output:**
- Clusters, each with:
  - Label (emergent from questions)
  - Uncertainty type: `causes | constraints | unknowns | dependencies | risks | options`
  - Questions in cluster
  - One-sentence insight
- Unclustered questions (if any)

**Triggers when:** User signals done with question collection.

**Renders:** Widget for cluster display + selection.

---

## Widget

### `cluster-display.html`

**Purpose:** Visual display of question clusters. User selects one to explore.

**Behavior:**
1. Render clusters as cards (collapsed by default)
2. Tap to expand → show questions
3. Tap "Explore this" → submit selection
4. Selection triggers closing reflection from LLM

**Styling:** OpenAI Design Tokens (same patterns as Clarity widget)

**Accessibility:** Keyboard nav, ARIA labels, VoiceOver tested

---

## Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Persistence | None (session-only) | Unpack is a single thinking pass, not a workspace. No user data to manage. |
| OAuth | None (`noauth`) | No persistence = no user identity needed |
| Backend | FastMCP (Python) | Consistency with Clarity; proven patterns |
| Widget framework | React + OpenAI Apps SDK UI | Consistency with Clarity; required for SDK |
| Hosting | Render | Existing infrastructure; fast deploys |
| Clustering logic | LLM-facilitated semantic clustering | Tool structures the output schema; LLM groups questions by meaning + uncertainty type. No embeddings needed. |
| Database | None | Session-only = no DB |
| Iteration | None — single pass only | No looping back to Step 1, no editing after clustering. Restart = new session. |

---

## Technical Constraints

1. **MCP tools cannot set system instructions** — LLM behavior shaped via `assistant_guidance` in `structuredContent`

2. **Widget runs in sandboxed iframe** — No localStorage, limited APIs, must use `window.openai.*`

3. **Tool descriptions control WHEN tools are called** — Must be precise to avoid misfires

4. **`assistant_guidance` controls WHAT LLM says after tool** — Embed exact phrasing and constraints

5. **ChatGPT caches aggressively** — Use versioned resource URIs for widgets

---

## Failure Modes (How to Handle Edge Cases)

| Situation | Response |
|-----------|----------|
| Problem formulation confidence is low | Ask ONE clarifying question, then proceed anyway with best interpretation |
| User provides < 3 questions | Do not call `cluster_questions`. Prompt for more. |
| User provides 3-4 questions | Accept as valid. Prompt once for more, then proceed. |
| Clustering yields only 1 cluster | Label it as "dominant uncertainty" — still valid output |
| All questions fall into same type | Surface this as an insight: "Your questions center on [type]" |
| Questions are incoherent/unrelated | Create an "unclustered" group, surface it honestly |
| User selects cluster but asks to go back | Politely decline. Restart = new session. |

**Principle:** When uncertain, proceed with honesty rather than inventing structure.

---

## LLM Behavior Rules (Non-Negotiable)

The LLM must:
- **Facilitate, never advise**
- **Ask, never tell**
- **Reflect, never prescribe**

Forbidden phrases:
- "You should..."
- "I recommend..."
- "The best option is..."
- "Here's what to do..."
- "You might want to..." (this is advice in disguise)

Allowed:
- "Here's what I'm hearing..."
- "These questions suggest..."
- "What would you need to understand before...?"
- "What stands out to you?"

**Step 4 Closing — Reflection Question Examples:**

❌ Wrong: "You might want to talk to your manager"
✅ Right: "What would you need to understand before talking to your manager?"

❌ Wrong: "Consider researching market rates"
✅ Right: "What's one thing you could learn this week that would change how you see this?"

---

## Quality Gates (All Increments)

Before any increment is complete:
- [ ] Tool returns valid schema per spec
- [ ] Tool description triggers at correct moments (test with golden prompts)
- [ ] `assistant_guidance` produces facilitator-style responses
- [ ] No advice, no solutions in LLM output
- [ ] MCP Inspector validates tool response

Before submission:
- [ ] Widget renders correctly on web, iOS, Android
- [ ] Keyboard navigation works
- [ ] VoiceOver reads correctly
- [ ] Full flow completes end-to-end
- [ ] Demo video recorded

---

## What This App Is NOT Building

- User accounts
- Data persistence
- Save/load
- Multiple sessions
- Analytics
- Complex NLP
- Integration with other apps

**Scope is locked. Ship fast.**

---

## Reference: Uncertainty Types

| Type | Questions About | Example |
|------|-----------------|---------|
| `causes` | Why something happens | "Why do I keep saying yes to low-paying work?" |
| `constraints` | What limits options | "What's stopping me from raising rates?" |
| `unknowns` | Missing information | "What are others in my field charging?" |
| `dependencies` | Other people/factors | "How would my clients react?" |
| `risks` | What could go wrong | "What if I lose clients?" |
| `options` | Possible paths forward | "What are my alternatives?" |

---

## Increment Overview

| # | Scope | Output |
|---|-------|--------|
| 1 | Server foundation + `formulate_problem` | Working tool in MCP Inspector |
| 2 | `cluster_questions` tool | Working tool in MCP Inspector |
| 3 | Widget implementation | Widget renders + accepts selection |
| 4 | Integration + testing + submission | Submitted to OpenAI |

Each increment has its own briefing. This document is the shared context.