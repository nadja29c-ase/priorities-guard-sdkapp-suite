Claude Code Briefing: Implement Message Rotation
Objective
Replace static message with random.choice() from message arrays. LLM follows content message reliably; variants in structuredContent are ignored.

Safety First
bashgit add -A && git commit -m "checkpoint: before message rotation implementation"

File 1: mcp_server/clarity/tool_logic.py
Add import at top:
pythonimport random
Replace the organize_thoughts function with rotation logic:
For thoughts_exhausted=False branch:
Define message array (before function or as module constant):
pythonELICIT_MORE_MESSAGES = [
    "Good — that's already taking shape. Let's get everything out so nothing keeps spinning. What else is on your mind?",
    "You're getting it out of your head and onto the board — that's how overwhelm shrinks. Anything else?",
    "More clarity with each one. We want the full picture before prioritizing. What other thoughts are taking up space?",
    "The picture's forming. Better to capture it all now than have it pop up later. Any loose threads?",
    "That's a few clusters already. Once it's all out, you can actually see what you're dealing with. What else is bouncing around?",
    "Nice — thoughts dumped, clusters formed. Any loose threads before we focus in?",
]
In function: message = random.choice(ELICIT_MORE_MESSAGES)
For thoughts_exhausted=True branch:
Define message array:
pythonTRANSITION_TO_PRIORITIZE_MESSAGES = [
    "Everything's out and organized — you can see the full picture now. Clarity doesn't come from seeing it all. It comes from knowing where to focus. So, what matters most right now: making progress toward a goal, unblocking something stuck, or getting relief from what's weighing on you?",
    "You've done the hard part — it's all out of your head. Overwhelm doesn't shrink by organizing. It shrinks by choosing. What would help most right now: moving toward a goal, clearing a blocker, or just getting some relief?",
    "Your Clarity Board is ready. Next step isn't doing more — it's deciding less. Are you chasing a goal, trying to get unstuck, or just need some weight off your shoulders?",
]
In function: message = random.choice(TRANSITION_TO_PRIORITIZE_MESSAGES)
Remove variants from both branches — no longer needed.
Keep guidance as-is — it controls behavior, not the opening message.

File 2: mcp_server/clarity/tools/prioritize_clusters.py
Add import at top:
pythonimport random
Define closure messages (after constants section):
pythonPRIORITIZE_CLOSURE_MESSAGES = [
    "There — your priorities are set. The noise just got quieter. That's your Clarity board — saved and ready to revisit anytime.",
    "Priorities locked in. You've cut through the clutter. Your board is ready — come back to it whenever you need to refocus.",
    "Done. You know where to focus now. That's your Clarity board — load it anytime to pick up where you left off.",
]
In handle() function, replace the static message build:
Current (around line 240):
pythonif priority_count == 0:
    message = "Priorities cleared from board."
else:
    ranks = [p.rank for p in request.priorities]
    message = f"Applied {priority_count} priorit{'y' if priority_count == 1 else 'ies'} ({', '.join(sorted(ranks))}) to board."
Replace with:
pythonif priority_count == 0:
    message = "Priorities cleared from board."
else:
    message = random.choice(PRIORITIZE_CLOSURE_MESSAGES)
Keep guidance as-is — it tells LLM how to mirror back and close.

Summary of Changes
FileChangetool_logic.pyAdd import random, add ELICIT_MORE_MESSAGES and TRANSITION_TO_PRIORITIZE_MESSAGES constants, use random.choice() for message, remove variantsprioritize_clusters.pyAdd import random, add PRIORITIZE_CLOSURE_MESSAGES constant, use random.choice() for success message

Do NOT Change

assistant_guidance content (controls behavior)
Tool descriptions
Input schemas
Handler registration
Any other files


Rollback
bashgit checkout -- mcp_server/clarity/tool_logic.py mcp_server/clarity/tools/prioritize_clusters.py