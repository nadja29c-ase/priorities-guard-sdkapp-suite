SHARPEN V1 — Technical Requirements

Overview
Sharpen is a stateless, single-session SDK app within the Priority Guardian Suite. No user accounts, no persistence, no OAuth. Value is delivered entirely through facilitated conversation + export.

Suite Integration
Sharpen V1 is part of the Priority Guardian monorepo.
Follows shared directory structure (backend/apps/sharpen/, mcp/sharpen/)
Uses shared config patterns
Deploys under shared domain (path-based routing)
Does NOT currently use: OAuth, Database, Redis, Celery
Architecture supports adding these without refactoring

Architecture Summary
┌─────────────────────────────────────────────────────┐
│                   ChatGPT                           │
│              (Conversation Layer)                   │
└─────────────────┬───────────────────────────────────┘
                  │
                  │ MCP Protocol
                  ▼
┌─────────────────────────────────────────────────────┐
│              Sharpen MCP Server                     │
│                                                     │
│  Tools:                                             │
│  ├── export_csv        → generates .csv file       │
│  ├── export_ics        → generates .ics file       │
│  └── export_checklist  → generates .md file        │
│                                                     │
│  No database. No state. No auth.                   │
└─────────────────────────────────────────────────────┘

Directory Structure (Monorepo)
priority-guardian/
├── backend/
│   ├── core/                    # Shared backend (OAuth, DB, etc.)
│   └── apps/
│       ├── focused/
│       ├── clarity/
│       └── sharpen/             # NEW
│           ├── __init__.py
│           └── tools.py         # File generation logic
│
├── mcp/
│   ├── focused/
│   ├── clarity/
│   └── sharpen/                 # NEW
│       ├── server.py            # FastMCP + tool registration
│       ├── config.py            # Environment config
│       └── resources/           # Widget HTML (V1.1)
│
├── widgets/
│   └── sharpen/                 # Deferred to V1.1
│
└── tests/
    └── sharpen/
        ├── unit/
        │   ├── test_export_csv.py
        │   ├── test_export_ics.py
        │   └── test_export_checklist.py
        └── integration/
            └── test_mcp_tools.py

Components
Component
V1
Notes
ChatGPT
✅
Hosts conversation, calls MCP tools
MCP Server
✅
Stateless, export-only
OAuth
❌
Not needed
Database
❌
No persistence
Widget
❌
Deferred to V1.1
Shared Backend
❌
Not used (architecture ready)


MCP Server Specification
Framework: FastMCP (Python)
Pattern: Follows Focused/Clarity MCP server structure

Tool 1: export_csv
Purpose: Generate CSV file for import into Asana/Monday/Notion
Input:
json
{
  "items": [
    {
      "task_name": "string",
      "description": "string (optional)",
      "estimate_hours": "number (optional)",
      "deliverable": "string",
      "due_date": "string (optional, YYYY-MM-DD)"
    }
  ]
}
```

**Output Schema:**
```
Task Name, Description, Estimate (hours), Deliverable, Due Date
Response Pattern:
json
{
  "structuredContent": {
    "status": "exported",
    "format": "csv",
    "item_count": 5,
    "assistant_guidance": {
      "action": "CONFIRM_EXPORT"
    }
  },
  "_meta": {
    "file_content_base64": "...",
    "filename": "sharpen_plan.csv",
    "mime_type": "text/csv"
  }
}

Tool 2: export_ics
Purpose: Generate .ics file for import into Google/Apple/Outlook calendar
Input: Same as export_csv
Output: Downloadable .ics file
Event format:
All-day events (no specific time)
SUMMARY = Task Name
DESCRIPTION = Description + Deliverable + Estimate
DTSTART = Due Date (if provided) or today
No time blocking
Response Pattern:
json
{
  "structuredContent": {
    "status": "exported",
    "format": "ics",
    "event_count": 5,
    "assistant_guidance": {
      "action": "CONFIRM_EXPORT"
    }
  },
  "_meta": {
    "file_content_base64": "...",
    "filename": "sharpen_plan.ics",
    "mime_type": "text/calendar"
  }
}

Tool 3: export_checklist
Purpose: Generate markdown checklist for copy-paste
Input: Same as export_csv
Output Format:
markdown
## [Deliverable Name]
- [ ] Task name (Xh)
- [ ] Task name (Xh)

## [Deliverable Name]
- [ ] Task name (Xh)
Response Pattern:
json
{
  "structuredContent": {
    "status": "exported",
    "format": "markdown",
    "item_count": 5,
    "checklist_markdown": "## Deliverable A\n- [ ] Task 1 (2h)\n...",
    "assistant_guidance": {
      "action": "CONFIRM_EXPORT"
    }
  }
}
```

Note: Checklist can be returned directly in `structuredContent` for LLM to display — no file download needed.

---

## Data Model (Session Only)

No persistence. Data exists only during the ChatGPT conversation.

The LLM builds this structure through facilitation, then passes to export tools:
```
Project
├── name: string
├── definition_of_done: string
└── deliverables: []
    ├── name: string
    ├── type: must-have | nice-to-have
    └── work_items: []
        ├── task_name: string
        ├── description: string
        ├── estimate_hours: number
        ├── committed: boolean
        └── due_date: string (optional)

Deployment
Aspect
Spec
Hosting
Render (shared with Priority Guardian)
Domain
priority-guard.com/mcp/sharpen/
Port
8001 (or next available in suite)
Auth
None
HTTPS
Required


Compliance
Requirement
V1 Status
GDPR
✅ No personal data stored
Data retention
✅ No data retained
Privacy policy
⚠️ Required for SDK app review
Terms of service
⚠️ Required for SDK app review

Privacy policy and ToS: "Sharpen does not store any user data. All planning data exists only within your ChatGPT conversation."

Out of Scope (V1)
User accounts
Session persistence
Project memory
Google Calendar direct integration (OAuth)
Widgets
Progress tracking
Any form of backlog management

Open Questions
Export delivery mechanism: Base64 in _meta? Temporary download URL? (Needs SDK capability check)
Due date handling: Does Sharpen ask user for target dates during facilitation, or leave blank?
Estimate granularity: Hours only? Allow "30 min" / "2 days"?

Future Expansion (V1.1+)
Feature
Adds
Widget
Visual plan display during session
Export history
Database table, user identity
Direct calendar integration
OAuth, Google Calendar API

Architecture supports all without refactoring.

Document Status: Final — Ready for Claude Code briefing

