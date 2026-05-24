Claude Code Briefing: Conditional Guidance in prioritize_clusters
Objective
Replace static closure guidance with conditional guidance based on priority_count.

File: mcp_server/clarity/tools/prioritize_clusters.py
Find this block in handle() function (near end, before return):
pythonguidance = (
    "Mirror back briefly: what clusters emerged, what was/seemed important to the user. "
    "Then say: 'That's your Clarity board — ready to be saved and revisited. "
    "You can come back to your board anytime by asking to load it. "
    "From here we're just chatting — ask me anything or close when you're done.' "
    "Then answer naturally."
)
Replace with:
pythonif priority_count == 0:
    guidance = "No priorities set. Ask which clusters feel most important to them right now."

elif priority_count == 1:
    guidance = """Nice — P1 is set. Acknowledge that they've named what matters most.

Then genuinely ask if there's a second priority pulling at them, or if one focus is enough right now. Let them decide — no pressure either way."""

elif priority_count == 2:
    guidance = """Two priorities locked in. Reflect that back — they're creating real focus.

Check if there's a third, but make it clear that two is perfectly fine. "Is there a P3, or does this feel complete?" """

else:  # 3
    guidance = """Three priorities — they've cut through the noise. Acknowledge that briefly.

Let them know their board is ready to save and come back to anytime. Then just be present — if they want to keep talking, talk. If they're done, that's fine too."""

Do NOT Change

priority_count = len(request.priorities) — already exists, use it
message variable
meta block
return statement
Anything else in the file


Verification
After change, the return statement should still use guidance:
pythonstructuredContent={
    "clusters": enriched_clusters,
    "assistant_guidance": guidance,  # ← This uses the conditional guidance
},Claude is AI and can make mistakes. Please double-check responses.