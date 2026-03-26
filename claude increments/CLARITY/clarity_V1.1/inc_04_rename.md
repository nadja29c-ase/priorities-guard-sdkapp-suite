Claude Code Briefing: Rename Clarity → MindSort AI
Before starting: Read OPERATIONS_PREDEPLOY.md.
Copy and adjust only — do not rewrite, restructure, or improve anything not listed.
This rename has two parts: files that require a widget rebuild, and files that don't.

Part 1 — Widget source files (require npm run build after changes)
mcp_server/clarity/widget-react/src/components/Header.tsx
Change:
tsx<p className="heading-sm text-default mb-1">Your Clarity Board</p>
To:
tsx<p className="heading-sm text-default mb-1">Your MindSort AI Board</p>
mcp_server/clarity/widget-react/src/App.tsx
Three changes:

Interface name:

tsx// Before
interface ClarityWidgetState {
// After
interface MindSortWidgetState {

Type cast (line: window.openai?.widgetState as ClarityWidgetState):

tsx// Before
const savedState = window.openai?.widgetState as ClarityWidgetState | undefined
// After
const savedState = window.openai?.widgetState as MindSortWidgetState | undefined

satisfies type (line: } satisfies ClarityWidgetState)):

tsx// Before
} satisfies ClarityWidgetState)
// After
} satisfies MindSortWidgetState)

Console error string:

tsx// Before
console.error('Clarity widget load error:', error)
// After
console.error('MindSort AI widget load error:', error)

aria-label on <main>:

tsx// Before
aria-label="Clarity Board"
// After
aria-label="MindSort AI Board"

Empty state message:

tsx// Before
No saved board yet. Start one by sharing what's on your mind in the chat.
// After (unchanged — this is fine as-is, no brand name here)
After all widget source changes: run npm run build in mcp_server/clarity/widget-react/ and copy the output to mcp_server/clarity/widgets/clarity-clusters.html.

Part 2 — Server and handler files (no rebuild needed)
mcp_server/clarity/server.py
Four changes:
python# Before
mcp = FastMCP("clarity-mcp", ...)
# After
mcp = FastMCP("mindsort-mcp", ...)
python# Before
return JSONResponse({"status": "ok", "service": "clarity-mcp"})
# After
return JSONResponse({"status": "ok", "service": "mindsort-mcp"})
python# Before
logger.info("clarity.server.shutdown")
# After
logger.info("mindsort.server.shutdown")
python# Before
logger.info("clarity.server.starting", ...)
# After
logger.info("mindsort.server.starting", ...)
python# Before
print("CLARITY MCP SERVER - V5 (Widget Integration)")
# After
print("MINDSORT AI MCP SERVER")
mcp_server/clarity/handlers/resources.py
Three changes:
python# Before
name="clarity_clusters_widget",
title="Clarity Clusters Widget",
# After
name="mindsort_clusters_widget",
title="MindSort AI Clusters Widget",
Same change in list_resource_templates() — identical fields, identical replacement.
The openai/widgetDescription strings don't mention "Clarity" by name — leave them unchanged.
mcp_server/clarity/tools/delete_my_data.py
Five string replacements in assistant_guidance values only — do not touch logic:
python# Before
"Permanently deletes the user's saved Clarity board"
# After
"Permanently deletes the user's saved MindSort AI board"

# Before (in DESCRIPTION)
"Permanently deletes the user's saved Clarity board. This cannot be undone."
# After
"Permanently deletes the user's saved MindSort AI board. This cannot be undone."

# Before
"The user's saved Clarity board has been permanently deleted"
# After
"The user's saved MindSort AI board has been permanently deleted"

# Before
"Your Clarity board has been deleted"
# After
"Your MindSort AI board has been deleted"

# Before
"Your Clarity data has been deleted"
# After
"Your MindSort AI data has been deleted"

# Before (appears twice in assistant_guidance strings)
"this tool only deletes Clarity data"
# After
"this tool only deletes MindSort AI data"

# Before (appears twice)
"clarity@priority-guard.com"
# After
"mindsort@priority-guard.com"

Part 3 — Docs (update in same commit, no deploy impact)
mcp_server/clarity/docs/SUBMISSION_CHECKLIST.md
markdown# Before
- [X] App name: Clarity
- [X] Support email: clarity@priority-guard.com
# After
- [X] App name: MindSort AI
- [X] Support email: mindsort@priority-guard.com
mcp_server/clarity/docs/REVIEWER_TESTING_GUIDE.md
markdown# Before
# Clarity — Reviewer Testing Guide
Add Clarity app from directory
"Delete all my Clarity data"
# After
# MindSort AI — Reviewer Testing Guide
Add MindSort AI app from directory
"Delete all my MindSort AI data"

Post-deploy manual steps (not Claude Code)

Create mindsort@priority-guard.com in Google Workspace
Update app name to MindSort AI in OpenAI developer portal
Update MCP server URL to https://mindsort.priority-guard.com/mcp in OpenAI portal