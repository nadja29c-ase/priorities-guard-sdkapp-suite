Claude Code Briefing: save_board Widget Output
Goal
Make save_board return a widget so both LLM and widget-button saves show "✓ Saved" correctly.
Changes
1. mcp_server/clarity/tools/save_board.py
Update DESCRIPTION - remove "WIDGET-ONLY" language:
pythonDESCRIPTION = """
Save the current Clarity board to the database.

WHEN TO CALL:
- User asks to save their board
- Widget Save button clicked

Returns the saved board with widget showing "✓ Saved" indicator.
"""
Update INPUT_SCHEMA - make confirmed optional:
python"required": ["clusters"]  # Remove "confirmed" from required
Update confirmed validation - default to True if missing:
pythonclass SaveBoardRequest(BaseModel):
    confirmed: bool = True  # Default to True
    clusters: List[ClusterInput]
    # Remove the @model_validator that rejects confirmed=false
Update success response - include clusters and widget metadata:
pythonreturn mcp_types.CallToolResult(
    content=[mcp_types.TextContent(
        type="text",
        text=f"Board saved successfully ({cluster_count} clusters)."
    )],
    structuredContent={
        "saved": True,
        "clusters": clusters_for_storage,  # ADD: widget needs this
        "saved_board_hash": content_hash,
    },
    _meta={  # ADD: widget metadata
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Saving your board...",
        "openai/toolInvocation/invoked": "Board saved.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    },
)
Update registration - add widget_uri:
pythonregister_tool(ToolDefinition(
    name=NAME,
    ...
    widget_uri=WIDGET_URI,  # ADD: produces widget
    widget_accessible=True,
    ...
))
Add import at top:
pythonfrom ..handlers.resources import WIDGET_URI
2. Remove ERROR_WIDGET_ONLY - no longer needed, delete the constant and any code referencing it.
Tests to Update
test_save_board.py:

Remove test_rejects_confirmed_false
Update tests expecting error_code == ERROR_WIDGET_ONLY
Add test verifying clusters in success response
Add test verifying _meta contains widget template

No Changes Needed

Widget HTML (already reads clusters + saved_board_hash from any tool output)
organize_thoughts
load_saved_board