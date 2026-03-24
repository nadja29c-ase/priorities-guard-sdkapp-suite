Here it is, complete and ready to hand to Claude Code:

Increment: Diagnostic — Surface raw callTool result on iOS

Purpose: All CRUD operations fail on iOS with "couldn't save". Works on desktop. Root cause unknown — we need to see the exact shape of the callTool response on iOS. This increment makes the error message display the raw response shape directly in the widget UI on iPhone.

⚠️ TEMPORARY DIAGNOSTIC BUILD — must be fully reverted before submission.

Scope: One file, one function only.

File: mcp_server/priority_guardian/widget-react/src/App.tsx

Function: handleToggleDeliverable

Change: Find this exact block inside handleToggleDeliverable:

ts
if (result?.isError) {
  throw new Error("Couldn't save. Try again.")
}

const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

if (!content?.data) {
  throw new Error("Couldn't save. Try again.")
}
Replace it with:

ts
// TODO: REMOVE BEFORE SUBMISSION — diagnostic only
if (result?.isError) {
  let safe = '[unserializable]'
  try { safe = JSON.stringify(result).slice(0, 200) } catch { /* noop */ }
  throw new Error(`[isError] keys=${Object.keys((result as object) ?? {}).join(',')} | ${safe}`)
}

const content = extractStructuredContent<{ data?: ToolOutputData }>(result)

// TODO: REMOVE BEFORE SUBMISSION — diagnostic only
if (!content?.data) {
  let safe = '[unserializable]'
  try { safe = JSON.stringify(result).slice(0, 200) } catch { /* noop */ }
  throw new Error(`[noData] keys=${Object.keys((result as object) ?? {}).join(',')} | ${safe}`)
}
Constraints:

No other CRUD handlers are touched
Do not modify extractStructuredContent in utils.ts
Do not remove the existing [PG:*] console logs
Do not add any other changes
Tests: None required — diagnostic-only change with no logic impact.

Read OPERATIONS_PREDEPLOYMENT.md before committing.

