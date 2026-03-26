Claude Code Briefing: Test Message Variants in assistant_guidance
Objective
Test hypothesis: LLM ignores content when structuredContent is present. Put message variants inside assistant_guidance instead.

Step 1: Safety Backup
bashcp mcp_server/clarity/tool_logic.py mcp_server/clarity/tool_logic_BACKUP.py
git add -A && git commit -m "checkpoint: before assistant_guidance variants test"

Step 2: Modify mcp_server/clarity/tool_logic.py
For thoughts_exhausted=False branch, replace:
pythonmessage = "What else is on your mind?"
guidance = "🛑 STOP - NO ADVICE - Instead, acknowledge what's been captured, note progress toward clarity, then ask for more thought items. Stay warm."
variants = [...]
With:
pythonmessage = ""  # Empty - model ignores this anyway
guidance = """🛑 STOP - NO ADVICE - Acknowledge progress warmly, then ask for more thoughts.

Use one of these naturally (vary each time):
- "Good — that's taking shape. Let's get everything out. What else is on your mind?"
- "You're getting it out of your head — that's how overwhelm shrinks. Anything else?"
- "The picture's forming. Better to capture it all now. Any loose threads?"
- "That's a few clusters already. Once it's all out, you can see what you're dealing with. What else?"

No advice. No task lists. Just acknowledge + ask."""
For thoughts_exhausted=True branch, replace:
pythonmessage = "Here's your Clarity Board..."
guidance = """Acknowledge the user's feelings..."""
variants = [...]
With:
pythonmessage = ""  # Empty - model ignores this anyway
guidance = """Acknowledge the user's work, then ask what matters most.

Use one of these naturally:
- "Everything's out and organized. Clarity comes from knowing where to focus. What matters most right now: progress toward a goal, unblocking something stuck, or relief from what's weighing on you?"
- "You've done the hard part — it's all out. What would help most: moving toward a goal, clearing a blocker, or getting some relief?"
- "Your board is ready. Are you chasing a goal, trying to get unstuck, or just need weight off your shoulders?"

EXAMPLE FLOW:
User: 'Relief'
You: 'Looking at your board — which cluster would bring the most relief?'
User: 'Billing'
You: 'Billing - got it. That's P1. What about P2?'
...

DO NOT explore root causes. Get P1/P2/P3 names, then call prioritize_clusters."""
Remove variants variable entirely — no longer needed.
Remove question_variants from result dict:
python# DELETE these lines:
if variants:
    result["structuredContent"]["question_variants"] = variants

Step 3: Test
Deploy and test with prompt:

"Review active client projects. Respond to client emails. Send invoices. Follow up on payments."

Success criteria:

LLM uses one of the variant phrases naturally
LLM asks a question (not robotic)
No advice given


Step 4: Rollback (if needed)
bashcp mcp_server/clarity/tool_logic_BACKUP.py mcp_server/clarity/tool_logic.py

Do NOT Change

enrich_clusters function
structuredContent.clusters structure
structuredContent.thoughts_exhausted field
Any other files
