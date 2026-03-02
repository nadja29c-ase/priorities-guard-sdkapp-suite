Refactor assistant_guidance in get_patterns to be composed per-pattern
File: mcp_server/priority_guardian/tools/get_patterns.py
Context: Currently GUIDANCE_PATTERNS_FOUND is one monolithic string covering all 4 pattern types. The LLM receives this entire blob regardless of which patterns actually fired, and has to figure out which sections apply. This degrades narration quality — especially when multiple patterns fire simultaneously. Each pattern has different narration goals, different data to reference, different pitfalls to avoid.
What to change:
Replace the single GUIDANCE_PATTERNS_FOUND constant with:

A GUIDANCE_COMMON constant — short, applies to every patterns-found response. Contains:

Keep it conversational. No bullet points, no headers, no numbered lists. Weave patterns into a natural narrative.
Observed numbers ("0.5h/week", "6-week streak", "22% growth") are good — state them. Internal thresholds and computation rules must never be mentioned.
Do not use the word "abandoned" — paraphrase neutrally (e.g., "getting very little time lately").
Do not repeat any internal field names or identifiers from the data verbatim — use the narration_label or your own phrasing instead.
If a pattern has calendar_keyword null, refer to the priority by name only — do not mention a keyword.
For retired priorities, frame the pattern as historical ("before you retired it" or "when it was active") — do not imply the pattern is ongoing.
Do not compute or invent patterns beyond what this response contains.


Four per-pattern guidance constants, one for each pattern_type:
GUIDANCE_CONSISTENCY_STREAK:

The dashboard already shows the streak count — do not just restate it.
Look at the actual_hours vs target_hours across the streak weeks in the data.
If some weeks fell significantly below target but the user still logged time, acknowledge that showing up consistently matters more than hitting the target every week. If hours are steady, note the reliability.
If the streak is 4+ weeks, note that this has moved past initial motivation into habit territory — the weeks where hours were lowest are actually the most telling because the user kept going anyway.
Keep it to 2-3 sentences max.

GUIDANCE_ABANDONED_PRIORITY:

State the observed average hours neutrally.
Ask what the user wants to do about it — do not prescribe action.
Do not judge. Do not say "you should retire this" or "you're neglecting this."
Keep it to 1-2 sentences plus a question.

GUIDANCE_PRIORITY_SWITCHING:

Present both interpretations: this could be healthy pivoting and adapting, or it could signal difficulty committing.
Ask what's been driving the changes.
Do not lean toward either interpretation — present them equally.
Keep it to 2-3 sentences.

GUIDANCE_PRIORITY_PROTECTION:

Acknowledge warmly that the user protected this priority's time despite growing calendar pressure.
Reference the observed numbers: priority hours stayed at ~Xh/week while total calendar grew Y%.
This is a positive signal — the user is defending what matters to them.
Keep it to 1-2 sentences.


A mapping dict from pattern_type string to its guidance constant:

   PATTERN_GUIDANCE = {
       "consistency_streak": GUIDANCE_CONSISTENCY_STREAK,
       "abandoned_priority": GUIDANCE_ABANDONED_PRIORITY,
       "priority_switching": GUIDANCE_PRIORITY_SWITCHING,
       "priority_protection": GUIDANCE_PRIORITY_PROTECTION,
   }
Change _build_assistant_guidance:
For the PATTERNS_FOUND case:

Start with GUIDANCE_COMMON
Iterate over data["patterns"], look up each pattern's pattern_type in PATTERN_GUIDANCE
Append each matched per-pattern guidance, prefixed with a label like "[Consistency Streak]:" so the LLM knows which guidance maps to which pattern
Skip unknown pattern_types (forward-compatible)
Join everything with double newline separators

The INSUFFICIENT_WEEKS and NO_PATTERNS paths remain unchanged.
Do not change:

pattern_service.py (backend computation)
Pattern data structure or response shape
Handler logic in handle()
Tool definition or input schema
Any other tool file

Unit tests:
Test 1: Single pattern (consistency_streak) → guidance contains GUIDANCE_COMMON + GUIDANCE_CONSISTENCY_STREAK, does NOT contain guidance text for other pattern types.
Test 2: All 4 patterns present → guidance contains GUIDANCE_COMMON + all 4 per-pattern guidance blocks.
Test 3: No patterns (reason=NO_PATTERNS) → guidance is GUIDANCE_NO_PATTERNS, no per-pattern guidance.
Test 4: Insufficient weeks → guidance uses GUIDANCE_INSUFFICIENT_DATA_TEMPLATE, no per-pattern guidance.
Test 5: Unknown pattern_type in data → skipped gracefully, no error, other patterns still get guidance.