Claude Code Briefing: Priority-Count Based Messages
Objective
Add conditional message rotation in prioritize_clusters based on how many priorities are set (1, 2, or 3). Messages should be lens-neutral (not assuming relief/goal/unblocking).

File: mcp_server/clarity/tools/prioritize_clusters.py
Add message constants after existing constants section (~line 40):
python# ============================================================================
# Response Messages (rotated by priority count)
# ============================================================================

P1_SET_MESSAGES = [
    "P1 is set — you've named what matters most right now. What about P2?",
    "Got it. First priority locked in. Is there a second one, or is one enough for now?",
    "P1 done. You're creating focus. Anything else that deserves P2?",
]

P2_SET_MESSAGES = [
    "P1 and P2 are set. Clear focus areas. Is there a P3, or are two enough?",
    "Two priorities locked in. Do you want to add a third, or does this feel complete?",
    "Focus is forming. Any third priority, or are you good with two?",
]

PRIORITIZE_CLOSURE_MESSAGES = [
    "Three priorities set. You know where to focus now.",
    "P1, P2, P3 — done. That's your Clarity board.",
    "All set. Three clear focus areas. That's clarity.",
]
In handle() function, replace the message/guidance block (around line 240):
Current:
pythonpriority_count = len(request.priorities)
if priority_count == 0:
    message = "Priorities cleared from board."
else:
    ranks = [p.rank for p in request.priorities]
    message = f"Applied {priority_count} priorit{'y' if priority_count == 1 else 'ies'} ({', '.join(sorted(ranks))}) to board."
Replace with:
pythonpriority_count = len(request.priorities)

if priority_count == 0:
    message = "Priorities cleared from board."
    guidance = "Ask user which clusters they want to prioritize."

elif priority_count == 1:
    message = random.choice(P1_SET_MESSAGES)
    guidance = "User set P1. Ask about P2. Give permission to stop if one is enough."

elif priority_count == 2:
    message = random.choice(P2_SET_MESSAGES)
    guidance = "User set P1 and P2. Ask if there's a P3 or if two is enough."

else:  # 3
    message = random.choice(PRIORITIZE_CLOSURE_MESSAGES)
    guidance = (
        "Mirror back briefly: what clusters emerged, what user prioritized. "
        "Say: 'That's your Clarity board — ready to save and revisit anytime. "
        "You can come back by asking to load it.' Then chat naturally."
    )
Remove the old static guidance definition that currently sits after the message block — it's now defined conditionally above.
Ensure import random is at top of file.

Do NOT Change

Input schema
Tool description
Validation logic
Helper functions
Handler registration


Expected Behavior
User actionTool called withMessageNext step"P1 is Billing"priorities: [P1]"P1 done. What about P2?"LLM asks for P2"Client Comm is P2"priorities: [P1, P2]"P1, P2 set. Any P3?"LLM asks about P3"No, two is enough"— (no tool call)—LLM closes naturally"Project Oversight"priorities: [P1, P2, P3]"Three priorities set."LLM mirrors + closes