CLAUDE CODE BRIEFING — Clarity MCP Server (Draft 1)
Context

Project: Priority Guardian SDK App Suite
 New Component (new sdk app): Clarity MCP Server
 Purpose: Validate tool invocation and output quality before investing in persistence or UI widgets
 Testing Mode: Local development (MCP Inspector + ChatGPT Developer Mode via ngrok)
 Authentication: DISABLED — Anonymous mode, no OAuth

Goal
Add a standalone MCP server for Clarity within the Priority Guardian folder structure. Implement a single tool that turns unstructured business brain dumps into structured clarity output.
This is a validation prototype only. We're testing:
Whether ChatGPT reliably calls the tool
Whether the output schema feels valuable
Whether the tool description triggers correctly

Scope Clarification
We are building an MCP SERVER only, not a full SDK app.
✅ MCP server with one tool
❌ NO manifest.json
❌ NO UI widgets
❌ NO backend REST endpoints
❌ NO database
❌ NO authentication

Architecture
Priority Guardian has:
Main FastAPI backend on port 8000
Focused MCP server on port 8001
Clarity will:
Live in backend/apps/clarity/
Run its own MCP server on port 8002
Run completely standalone (no dependencies on backend)
Accept anonymous requests (no auth)

CRITICAL: What to Reuse vs. Avoid
✅ DO Reuse from Focused
Folder structure pattern (mcp_server.py, mcp_standalone.py, tools.py)
FastMCP initialization style
Standalone HTTP server runner pattern
General code organization
❌ DO NOT Reuse or Import
OAuth/JWT token validation
JWKS verification
User identity extraction (X-User-ID headers)
Token refresh logic
oauth_provider modules
Redis client usage
Celery task imports
Google Calendar logic
Any backend REST API calls
Database session/connection code
Authentication: Explicitly Disabled
This draft runs in ANONYMOUS mode. The MCP server must:
Set stateless_http=True in FastMCP config
NOT validate any Authorization headers
NOT import or use oauth_provider modules
NOT extract user identity
Accept ALL requests without authentication

File Structure to Create
backend/apps/clarity/
├── __init__.py
├── mcp_server.py      # FastMCP server with create_clarity tool
├── mcp_standalone.py  # Standalone runner for port 8002
└── tools.py           # Tool logic (static mock output)


Tool Specification
Tool Name
create_clarity_next_steps
Description (Critical for ChatGPT Discovery)
Turn a freelancer's unstructured brain dump into meaningful clusters and actionable next steps. Use this tool whenever the user:
- feels overwhelmed or scattered
- wants to figure out what to focus on
- asks for help organizing their thoughts
- shares a brain dump about their business
- says things like "I have too much going on" or "what should I prioritize"

Do NOT answer with plain text. This tool produces the official Clarity output with clusters and next steps.

Input Schema
{
  "type": "object",
  "properties": {
    "raw_text": {
      "type": "string",
      "description": "The unstructured brain dump containing mixed thoughts, tasks, ideas, or concerns. Business-focused."
    },
    "goal": {
      "type": "string",
      "description": "Optional: The user's current business goal (e.g. grow revenue, launch product). If not provided, AI infers from context or asks the user."
    }
  },
  "required": ["raw_text"]
}

Output Schema (Full Version)
{
  "type": "object",
  "properties": {
    "atomic_items": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Extracted concise tasks or thoughts from the raw input"
    },
    "clusters": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "summary": { "type": "string" },
          "items": { 
            "type": "array", 
            "items": { "type": "string" } 
          },
          "relevance_score": { 
            "type": "integer",
            "minimum": 1,
            "maximum": 10
          },
          "why_relevant": { "type": "string" }
        },
        "required": ["name", "summary", "items", "relevance_score", "why_relevant"]
      }
    },
    "top_clusters": {
      "type": "array",
      "maxItems": 3,
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "items": { "type": "array", "items": { "type": "string" } },
          "relevance_score": { "type": "integer" },
          "summary": { "type": "string" },
          "why_relevant": { "type": "string" }
        }
      }
    },
    "next_steps": {
      "type": "array",
      "maxItems": 5,
      "items": {
        "type": "object",
        "properties": {
          "step": { "type": "string" },
          "source_cluster": { "type": "string" },
          "effort": { 
            "type": "string",
            "enum": ["low", "medium"]
          },
          "estimated_minutes": { 
            "type": "integer",
            "enum": [5, 10, 15, 30]
          }
        },
        "required": ["step", "source_cluster", "effort", "estimated_minutes"]
      }
    },
    "clarity_summary": {
      "type": "string",
      "description": "3-4 sentence narrative explaining what matters most right now"
    },
    "confidence": {
      "type": "number",
      "minimum": 0,
      "maximum": 1
    }
  },
  "required": ["atomic_items", "clusters", "top_clusters", "next_steps", "clarity_summary", "confidence"]
}


Implementation: Static Mock Output
For this draft, the tool returns a hardcoded response regardless of input. This validates plumbing before adding AI logic.
In tools.py:
MOCK_CLARITY_OUTPUT = {
    "atomic_items": [
        "Update website homepage",
        "Email past clients about new offer",
        "Finish proposal for Client ABC",
        "Research competitor pricing",
        "Schedule social media posts",
        "Fix booking form bug"
    ],
    "clusters": [
        {
            "name": "Marketing & Outreach",
            "summary": "Activities to attract and retain clients",
            "items": ["Email past clients about new offer", "Schedule social media posts"],
            "relevance_score": 8,
            "why_relevant": "Direct path to revenue - reaching people who already trust you"
        },
        {
            "name": "Client Delivery",
            "summary": "Active client work with deadlines",
            "items": ["Finish proposal for Client ABC"],
            "relevance_score": 9,
            "why_relevant": "Immediate deadline, direct revenue impact"
        },
        {
            "name": "Website & Tech",
            "summary": "Digital presence and tools",
            "items": ["Update website homepage", "Fix booking form bug"],
            "relevance_score": 6,
            "why_relevant": "Important but not urgent unless blocking conversions"
        },
        {
            "name": "Research",
            "summary": "Information gathering",
            "items": ["Research competitor pricing"],
            "relevance_score": 4,
            "why_relevant": "Useful context but doesn't move needle directly"
        }
    ],
    "top_clusters": [
        {
            "name": "Client Delivery",
            "items": ["Finish proposal for Client ABC"],
            "relevance_score": 9,
            "summary": "Active client work with deadlines",
            "why_relevant": "Immediate deadline, direct revenue impact"
        },
        {
            "name": "Marketing & Outreach",
            "items": ["Email past clients about new offer", "Schedule social media posts"],
            "relevance_score": 8,
            "summary": "Activities to attract and retain clients",
            "why_relevant": "Direct path to revenue - reaching people who already trust you"
        },
        {
            "name": "Website & Tech",
            "items": ["Update website homepage", "Fix booking form bug"],
            "relevance_score": 6,
            "summary": "Digital presence and tools",
            "why_relevant": "Important but not urgent unless blocking conversions"
        }
    ],
    "next_steps": [
        {
            "step": "Draft 3 key points for Client ABC proposal",
            "source_cluster": "Client Delivery",
            "effort": "medium",
            "estimated_minutes": 30
        },
        {
            "step": "Write 2-sentence email to 3 past clients",
            "source_cluster": "Marketing & Outreach",
            "effort": "low",
            "estimated_minutes": 15
        },
        {
            "step": "Test booking form and note the bug",
            "source_cluster": "Website & Tech",
            "effort": "low",
            "estimated_minutes": 10
        }
    ],
    "clarity_summary": "Your highest priority is finishing the Client ABC proposal - it has a deadline and direct revenue impact. After that, quick outreach to past clients is your best marketing ROI. The website updates can wait unless the booking form is actively losing you leads.",
    "confidence": 0.85
}


def create_clarity_logic(raw_text: str, goal: str | None = None) -> dict:
    """
    Returns static mock output for testing.
    In future versions, this will process raw_text with AI.
    """
    # For now, ignore input and return mock
    return MOCK_CLARITY_OUTPUT


Server Implementation
In mcp_server.py:
"""
Clarity MCP Server - Draft 1
Standalone MCP server with no authentication.
"""
import logging
from mcp.server.fastmcp import FastMCP

from .tools import create_clarity_logic

# Configure logging (stdout is fine for HTTP servers)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP - NO authentication
mcp = FastMCP(
    name="clarity",
    stateless_http=True,
)


@mcp.tool()
async def create_clarity_next_steps(raw_text: str, goal: str | None = None) -> dict:
    """
    Turn a freelancer's unstructured brain dump into meaningful clusters 
    and actionable next steps. Use this tool whenever the user:
    - feels overwhelmed or scattered
    - wants to figure out what to focus on
    - asks for help organizing their thoughts
    - shares a brain dump about their business
    - says things like "I have too much going on" or "what should I prioritize"
    
    Do NOT answer with plain text. This tool produces the official Clarity 
    output with clusters and next steps.
    
    Args:
        raw_text: The unstructured brain dump containing mixed thoughts, 
                  tasks, ideas, or concerns. Business-focused.
        goal: Optional business goal (e.g. grow revenue, launch product).
              If not provided, AI infers from context.
    
    Returns:
        Structured clarity output with clusters, top_clusters, next_steps,
        and clarity_summary.
    """
    logger.info(f"create_clarity called with {len(raw_text)} chars")
    
    result = create_clarity_logic(raw_text, goal)
    
    logger.info(f"Returning {len(result['clusters'])} clusters, {len(result['next_steps'])} next steps")
    
    return result

In mcp_standalone.py:
"""
Standalone runner for Clarity MCP Server.
Run with: python -m backend.apps.clarity.mcp_standalone
"""
import uvicorn

from .mcp_server import mcp

if __name__ == "__main__":
    print("Starting Clarity MCP Server on port 8002...")
    print("Test with MCP Inspector: http://127.0.0.1:8002/mcp")
    
    uvicorn.run(
        mcp.get_app(),
        host="127.0.0.1",
        port=8002,
        log_level="info"
    )

In __init__.py:
"""Clarity MCP Server - Priority Guardian Suite"""


How to Run
Test 1: MCP Inspector
# Terminal 1: Start Clarity MCP server
cd priority-guardian
python -m backend.apps.clarity.mcp_standalone

# Terminal 2: Run MCP Inspector
npx @modelcontextprotocol/inspector@latest

# In Inspector:
# 1. Enter URL: http://127.0.0.1:8002/mcp
# 2. Click "List Tools" → should see create_clarity
# 3. Click "Call Tool" 
# 4. Enter raw_text: "I need to update my website, email clients, finish a proposal, research competitors"
# 5. Verify JSON output matches schema

Test 2: ChatGPT Developer Mode
# Terminal 1: Start server
cd priority-guardian
python -m backend.apps.clarity.mcp_standalone

# Terminal 2: Expose via ngrok
ngrok http 8002
# Copy the https URL (e.g., https://abc123.ngrok.app)

# In ChatGPT:
# 1. Settings → Connectors → Create
# 2. Name: "Clarity Test"
# 3. URL: https://abc123.ngrok.app/mcp
# 4. Click Create
# 5. Open new chat → Click + → Developer mode → Toggle on Clarity
# 6. Test prompts (see below)


Test Prompts
Should Trigger Tool ✅
"I'm feeling overwhelmed, here's what's on my mind: I need to update my website, email past clients, finish a proposal for ABC Corp, research competitor pricing, and schedule some social media posts"
"Help me figure out what to focus on next"
"Can you organize my thoughts? I have too many things going on"
"What should I prioritize this week? I'm scattered between client work, marketing, and admin stuff"
"Brain dump: website redesign, client invoices, new service offering, fix calendar booking, respond to leads"
Should NOT Trigger Tool ❌
"What's the weather today?"
"Write me an email to a client"
"Summarize this article"
"What time is it in Tokyo?"
"Help me write a blog post"

Acceptance Criteria
Test 1 (MCP Inspector)
[ ] Server starts on port 8002 without errors
[ ] create_clarity_next_steps tool appears in tool list
[ ] Manual invocation with sample raw_text returns valid JSON
[ ] Output contains all required fields: atomic_items, clusters, top_clusters, next_steps, clarity_summary, confidence
Test 2 (ChatGPT Developer Mode)
[ ] Connector creates successfully with ngrok URL
[ ] ChatGPT calls tool when user provides brain dump
[ ] ChatGPT asks for input if user just says "help me get clarity" without content
[ ] Output renders readably in chat
[ ] Clusters and next_steps feel meaningful (subjective)
[ ] Tool does NOT trigger on unrelated prompts

Do NOT Implement
❌ OAuth / JWT authentication
❌ Token validation middleware
❌ User identity resolution
❌ Database persistence
❌ Redis caching
❌ UI widgets / components
❌ manifest.json
❌ Multiple tools
❌ External API calls
❌ Celery jobs
❌ Backend REST endpoints
❌ Any imports from core.oauth_provider
❌ Any imports from core.db
❌ Any imports from core.redis_client

Dependencies
Use the same MCP packages as Focused:
fastmcp
uvicorn

Check requirements.txt in Priority Guardian for exact versions. Do NOT add the full requirements.txt — only MCP-related packages.

Import Conventions
All imports within Clarity must be relative:
# ✅ Correct
from .tools import create_clarity_logic

# ❌ Wrong - breaks standalone scripts
from backend.apps.clarity.tools import create_clarity_logic


Production Isolation
This server is NOT part of the production build.
NOT mounted in the main PG backend router
NOT exposed under /mcp or /clarity via reverse proxy
NOT referenced in main.py
Only started manually via mcp_standalone.py in local dev
This avoids accidental entanglement with production routing (port 8000/8001).

Logging Clarification
This MCP server uses HTTP transport (Uvicorn), not STDIO-based JSON-RPC.
print() is safe during development (does not corrupt protocol)
Structured logging is preferred but not required for this draft
Do NOT apply Focused's strict STDIO logging constraints

Tool Naming
Tool name MUST remain exactly: create_clarity
Do NOT rename to PascalCase (CreateClarity)
Do NOT add prefixes (clarity_create_clarity)
Keep it simple and lowercase with underscores

Implementation Pattern
Follow the identical startup pattern used in apps/focused/mcp_standalone.py:
uvicorn.run(mcp.get_app(), host="127.0.0.1", port=8002, ...)

Do NOT add:
Custom ASGI middleware
Alternative servers (hypercorn, gunicorn)
Additional routers or mounts

Expected File Sizes
Keep implementations minimal:
File
Expected Lines
mcp_server.py
60–120 lines
tools.py
40–80 lines
mcp_standalone.py
15–25 lines
__init__.py
1–3 lines

If significantly larger, you're overengineering.

Success Criteria
This draft is successful if:
Server runs without errors
MCP Inspector can list and call the tool
ChatGPT reliably calls the tool on trigger prompts
ChatGPT does NOT call the tool on unrelated prompts
The output structure feels valuable when rendered in chat
If all criteria pass → proceed to Draft 2 (AI-generated output instead of mock)

