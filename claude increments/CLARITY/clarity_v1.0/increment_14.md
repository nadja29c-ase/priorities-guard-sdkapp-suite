Claude Code Briefing: Test Simplified organize_thoughts_v2
Objective
Test if tool description alone guides LLM behavior without assistant_guidance.
Step 1: Safety
bashgit add -A && git commit -m "checkpoint: before organize_thoughts_v2 test"
Step 2: Create mcp_server/clarity/tools/organize_thoughts_v2.py
Copy from organize_thoughts.py, then:
Tool name: organize_thoughts_v2
INPUT_SCHEMA: Remove subclusters, tags. Keep only:

clusters (array of cluster_name + thought_items)
thoughts_exhausted (boolean, default false)

DESCRIPTION: Include facilitator role, ❌/✅ example, flow instructions.
Output: No assistant_guidance. Conditional content message:

If thoughts_exhausted=false: "What else is on your mind?"
If thoughts_exhausted=true: "Here's your board. Want to prioritize? Tell me which clusters matter most."

Step 3: Registration
In handler file (find where tools are registered):

Comment out organize_thoughts registration
Add organize_thoughts_v2 registration

Step 4: Test w. Chat Gpt
Rollback
bashgit checkout .