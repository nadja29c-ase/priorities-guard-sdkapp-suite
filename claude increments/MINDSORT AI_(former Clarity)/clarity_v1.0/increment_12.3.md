Claude Code Briefing: save_board render_widget Parameter
Goal
Add render_widget parameter to save_board (default=false). LLM-initiated saves should update existing widget, not render a new one.
Changes in mcp_server/clarity/tools/save_board.py
1. Update INPUT_SCHEMA:
python"render_widget": {
    "type": "boolean",
    "description": "If true, render widget with saved board. Default false."
}
2. Update SaveBoardRequest:
pythonclass SaveBoardRequest(BaseModel):
    confirmed: bool = True
    clusters: List[ClusterInput]
    render_widget: bool = False  # ADD

3. Update handle() success response:
python# Build response
structured = {
    "saved": True,
    "clusters": clusters_for_storage,
    "saved_board_hash": content_hash,
}

# Only include widget metadata if render_widget=True
if validated_request.render_widget:
    meta = {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Saving your board...",
        "openai/toolInvocation/invoked": "Board saved.",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }
else:
    meta = None

return mcp_types.CallToolResult(
    content=[...],
    structuredContent=structured,
    _meta=meta,
)
4. Update DESCRIPTION:
pythonDESCRIPTION = """
Save the current Clarity board to the database.

WHEN TO CALL:
- User asks to save their board
- Widget Save button clicked

Parameters:
- clusters: Board state to save
- render_widget: If true, show new widget. Default false (existing widget updates to show "✓ Saved")
"""
Test

Existing widget visible
User says "save my board"
LLM calls save_board (render_widget defaults to yesfalse)
No new widget appears
Existing widget shows "✓ Saved"