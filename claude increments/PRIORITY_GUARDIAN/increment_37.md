Increment: Remove unused timestamp fields from structuredContent output
Context
Pre-submission cleanup. Three fields are currently returned in get_priorities structuredContent that are never used by the widget or the LLM. They add noise to the payload and violate output minimization (compliance item #28).
What to remove
From mcp_server/priority_guardian/tools/get_priorities.py, in _normalize_priority():

createdAt (maps to created_at)
updatedAt (maps to updated_at)

From the same file, in the structuredContent assembly — the top-level data dict:

google_connected_at

What to NOT touch

id on priority, deliverable, goal — widget requires these for all mutations
Any other fields — functional, used by widget

Type cleanup
After removing from the Python layer, clean up the corresponding TypeScript types to match:

types.ts — remove createdAt: string and updatedAt?: string from Priority interface
types.ts — remove google_connected_at?: string from DashboardData interface
components/ConnectionStatus.tsx — remove connectedAt?: string from ConnectionStatusProps interface and from the function signature

Verification

Unit test: get_priorities tool response schema does not contain createdAt, updatedAt, or google_connected_at
TypeScript compiles without errors after type cleanup
Widget renders correctly — all CRUD operations (add/update/delete priority, deliverable, goal) still work (IDs still present)
No references to removed fields remain in widget source

Read OPERATIONS_PREDEPLOY.md before committing.