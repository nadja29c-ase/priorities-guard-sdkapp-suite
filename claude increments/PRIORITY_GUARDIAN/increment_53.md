Claude Code Task: Temporary iOS crash telemetry — diagnostic increment, remove before submission
Purpose: Add a temporary log_client_error MCP tool and widget instrumentation to capture client-side crash details on iOS via callTool and global error listeners. Root cause of the iOS crash is not yet confirmed. This entire increment — tool, registration, and all widget instrumentation — must be removed before store submission.

Change 1: New tool file
Create mcp_server/priority_guardian/tools/widget_tools/log_client_error.py, following the exact module structure of existing files in that directory (e.g. add_priority.py).
Tool definition at the bottom must be a ToolDefinition instance named LOG_CLIENT_ERROR with these properties:

name: "log_client_error"
description: "Internal diagnostic tool used by the widget to log client-side crash telemetry during debugging."
input_schema:

python{
    "type": "object",
    "properties": {
        "error_name":        {"type": "string"},
        "error_message":     {"type": "string"},
        "stack":             {"type": "string"},
        "component_stack":   {"type": "string"},
        "ua":                {"type": "string"},
        "phase":             {"type": "string"},
    },
    "additionalProperties": False,
}
No required fields.

required_scopes: ["pg.access"]
widget_uri: None
handle: see below
read_only_hint: True
destructive_hint: False
open_world_hint: False
widget_accessible: True
visibility: "private"

Handler: log all received fields at ERROR level via structlog, event key "widget.client_error". No backend HTTP call. Return mcp_types.CallToolResult with isError=False and a single TextContent with text "logged".

Change 2: Register the tool
mcp_server/priority_guardian/tools/widget_tools/__init__.py:

Add import for LOG_CLIENT_ERROR
Add to __all__

mcp_server/priority_guardian/tools/__init__.py:

Add LOG_CLIENT_ERROR to the import from .widget_tools
Add LOG_CLIENT_ERROR.name: LOG_CLIENT_ERROR to TOOL_REGISTRY


Change 3: Widget instrumentation
3a — Global error listeners in index.html (highest priority capture point)
In mcp_server/priority_guardian/widget-react/index.html, inject the following as the first <script> tag inside <head>, before everything else. This must be a plain (non-module) script so it runs before the module script:
html<script>
  window.__PG_ERRORS__ = [];

  window.onerror = function(message, source, lineno, colno, error) {
    var entry = {
      type: 'onerror',
      message: message || null,
      source: source || null,
      lineno: lineno || null,
      colno: colno || null,
      stack: (error && error.stack) ? error.stack.slice(0, 800) : null,
      ua: navigator.userAgent || null,
      phase: 'global_onerror',
    };
    window.__PG_ERRORS__.push(entry);
    try {
      if (window.openai && window.openai.callTool) {
        window.openai.callTool('log_client_error', {
          error_name: 'GlobalError',
          error_message: entry.message,
          stack: entry.stack,
          component_stack: (entry.source || '') + ':' + entry.lineno + ':' + entry.colno,
          ua: entry.ua,
          phase: 'global_onerror',
        })?.catch?.(function() {});
      }
    } catch(_) {}
    return false;
  };

  window.addEventListener('error', function(e) {
    var entry = {
      type: 'error',
      message: e.message || null,
      filename: e.filename || null,
      lineno: e.lineno || null,
      colno: e.colno || null,
      stack: (e.error && e.error.stack) ? e.error.stack.slice(0, 800) : null,
      ua: navigator.userAgent || null,
      phase: 'global_error',
    };
    window.__PG_ERRORS__.push(entry);
    try {
      if (window.openai && window.openai.callTool) {
        window.openai.callTool('log_client_error', {
          error_name: 'GlobalError',
          error_message: entry.message,
          stack: entry.stack,
          component_stack: (entry.filename || '') + ':' + entry.lineno + ':' + entry.colno,
          ua: entry.ua,
          phase: 'global_error',
        })?.catch?.(function() {});
      }
    } catch(_) {}
  });

  window.addEventListener('unhandledrejection', function(e) {
    var entry = {
      type: 'unhandledrejection',
      reason: e.reason ? String(e.reason).slice(0, 400) : null,
      ua: navigator.userAgent || null,
      phase: 'unhandled_rejection',
    };
    window.__PG_ERRORS__.push(entry);
    try {
      if (window.openai && window.openai.callTool) {
        window.openai.callTool('log_client_error', {
          error_name: 'UnhandledRejection',
          error_message: entry.reason,
          stack: null,
          component_stack: null,
          ua: entry.ua,
          phase: 'unhandled_rejection',
        })?.catch?.(function() {});
      }
    } catch(_) {}
  });
</script>
3b — ErrorBoundary callTool in main.tsx
In componentDidCatch, replace the entire fetch block (the try { fetch(...).catch(() => {}) } catch (_) {} block) with:
tstry {
  window.openai?.callTool?.('log_client_error', {
    error_name: error?.name ?? null,
    error_message: error?.message ?? null,
    stack: error?.stack?.slice(0, 800) ?? null,
    component_stack: errorInfo?.componentStack?.slice(0, 400) ?? null,
    ua: navigator?.userAgent ?? null,
    phase: 'error_boundary',
  })?.catch?.(() => {})
} catch (_) {}
Keep window.__PG_LAST_ERROR__ assignment. Remove the fetch block. Do not add a createRoot try/catch.
Also update the ErrorBoundary rendered output: replace PG_DEBUG_BOUNDARY_FIRED and BOUNDARY_ACTIVE_v5 with neutral user-facing text — something like "Dashboard unavailable" and "Please refresh to try again." Keep the inline styles.

Change 4: Bump widget URI
In mcp_server/priority_guardian/handlers/resources.py: bump WIDGET_URI from v6 to v7.
In mcp_server/priority_guardian/tools/widget_tools/add_priority.py: the WIDGET_URI constant at the top references v6 — update it to v7. Do not modify any other tool files.

After changes:

Rebuild widget: npm run build in mcp_server/priority_guardian/widget-react/
Verify the built widgets/pg-dashboard.html timestamp updates
Grep built HTML for log_client_error and __PG_ERRORS__ — both must be present
Grep built HTML for PG_DEBUG_BOUNDARY_FIRED — must NOT be present
Commit all changed files, push, wait for Render deploy on both MCP server and backend
Test on iOS — watch Render MCP server logs for widget.client_error entries; the phase field identifies where the crash occurs

Note: Telemetry only fires for authenticated sessions (pg.access scope). Test account is authenticated — sufficient for diagnostic purposes. If no widget.client_error log lines appear after the iOS crash, it means the crash happens before window.openai is available, which itself narrows the failure window significantly.