"""
Frame Initiative Intent Tool.

Captures WHO benefits, WHAT must exist, and WHY (the outcome).
All three are mandatory. Structural validation only — semantic quality is the LLM's job.
Self-registers at import time.
"""

from typing import Optional, Literal

import structlog
from mcp import types as mcp_types
from pydantic import BaseModel, ValidationError

from .base import ToolDefinition
from . import register_tool
from ..tool_logic import validate_initiative_intent

logger = structlog.get_logger(__name__)

# ============================================================================
# Tool Metadata (Goal-Oriented Description)
# ============================================================================

DESCRIPTION = """Records confirmed WHO, WHAT, and WHY of an initiative. This frames the initiative as outcome-focused so that later the amount of    
  work can be minimized based on outcome. Requires confidence="high".                                                                                  
                                                                                                                                                       
  SHARPEN MODE — BINDING RULES (not guidelines)                                                                                                        
  When user selects Sharpen, your default assistant behavior is SUSPENDED.                                                                             
                                                                                                                                                       
  SUSPENDED BEHAVIORS:                                                                                                                                 
  - Planning                                                                                                                                           
  - Offering options                                                                                                                                   
  - Suggesting answers                                                                                                                                 
  - Batching multiple questions                                                                                                                        
  - Proposing deliverables or tasks                                                                                                                    
  - "Being helpful" by front-loading structure                                                                                                         
                                                                                                                                                       
  ACTIVE BEHAVIORS:                                                                                                                                    
  - Ask ONE question at a time                                                                                                                         
  - Wait for answer                                                                                                                                    
  - Reflect their words back                                                                                                                           
  - Ask for user confirmation                                                                                                                          
  - Then call tool with confidence="high"                                                                                                              
                                                                                                                                                       
  These are not suggestions. These are operating constraints.                                                                                          
  Violating them means Sharpen is broken.                                                                                                              
                                                                                                                                                       
  CONFIDENCE EXAMPLES:                                                                                                                                 
    HIGH: who="The sales team" what="A CRM integration that syncs contacts daily" why="So sales reps spend less time on data entry". User confirmed,   
  outcome-phrased.                                                                                                                                     
    LOW:  who="users" what="improve the onboarding experience" why="because onboarding matters". Vague WHO, activity-based WHAT, motivation-phrased    
  WHY.                                                                                                                                                 
    LOW:  who="New hires" what="A checklist" why="So we can have a checklist". WHY restates WHAT — not valid.                                          
                                                                                                                                                       
  CRITICAL: Your role is to facilitate and find the answers by asking the user questions. NEVER suggest answers for the user. NEVER tell the user how  
  to frame the initiative correctly. Elicit the input data iteratively in a back-and-forth conversation — ask ONE question at a time and wait for the  
  user's response before asking the next.                                                                                                              
                                                                                                                                                       
  EXAMPLE CONVERSATION:                                                                                                                                
    User: "I want to improve our onboarding"                                                                                                           
    You: "Who specifically will benefit most from this improved onboarding?"                                                                           
    User: "New engineering hires"                                                                                                                      
    You: "What concrete thing will exist that doesn't exist today?"                                                                                    
    User: "A checklist they can follow in their first week"                                                                                            
    You: "So that new engineering hires benefit how?"                                                                                                  
    User: "So they can start contributing without constant interruptions"                                                                              
    You: "To confirm: New engineering hires need a first-week checklist so they can start contributing without constant interruptions. Correct?"       
    User: "Yes"                                                                                                                                        
    → Now call frame_initiative_intent with who="New engineering hires", what="A first-week onboarding checklist", why="So they can start contributing 
  without constant interruptions", confidence="high".
"""

INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "who": {
            "type": "string",
            "description": "ONE primary beneficiary. Who benefits first and foremost? Not multiple audiences. ACCORDING TO THE USER.",
        },
        "what": {
            "type": "string",
            "description": "WHAT artifact, deliverable, or handoff will exist when this initiative is finished to solve the WHY (Frame it as a hypothesis)? (concrete output=not activity) ACCORDING TO THE USER.",
        },
        "why": {
            "type": "string",
            "description": "So that WHO benefits HOW? Must be outcome-phrased (what changes), not motivation-phrased (why it matters). Lead with the pain if user not aware of the outcome; then reframe the pain into an outcome for the user. Do not restate WHAT — describe the change or benefit if this succeeds. ACCORDING TO THE USER.",
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
            "description": ("'high' = user has provided answers in their own words, that are specific. "
        "'low' = you inferred, assumed, used placeholders, or filled gaps. "
        "If user hasn't explicitly stated WHO/WHAT/WHY in their own words, confidence CANNOT be 'high'."),
        },
    },
    "required": ["who", "what", "why", "confidence"],
    "additionalProperties": False,
}


# ============================================================================
# Pydantic Models for Validation
# ============================================================================


class FrameIntentRequest(BaseModel):
    """Expected input structure from ChatGPT."""
    who: Optional[str] = None
    what: Optional[str] = None
    why: Optional[str] = None
    confidence: Optional[Literal["high", "medium", "low"]] = None


# ============================================================================
# Assistant Guidance Messages
# ============================================================================

GUIDANCE_CONFIDENCE_REJECTED = (
    "SHARPEN MODE STILL BINDING. "
    "Check which field is vague:\n"
    "- Vague WHO: Ask 'Who specifically is affected?'\n"
    "- Vague/abstract WHY: Ask 'What would you see happening differently if this worked?'\n"
    "- Vague WHAT: Ask 'What concrete thing would exist that doesn't exist today?'\n"
    "Ask ONE question. Then stop and wait. Do not explain, suggest, or plan."
)

GUIDANCE_MISSING_FIELDS = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question about the missing field using pain-first language:\n"
    "- Missing WHO: 'Who specifically is affected by this?'\n"
    "- Missing WHY: 'What's currently hard or frustrating for them?'\n"
    "- Missing WHAT: 'What do you think needs to exist to help with that?'\n"
    "Then stop and wait. Do not explain, suggest, or plan."
)

GUIDANCE_MULTIPLE_STAKEHOLDERS = (
    "SHARPEN MODE STILL BINDING. "
    "Multiple stakeholders detected. Ask: 'Who benefits first and foremost?' "
    "Then stop and wait. Frame confirmation as '[WHO] primarily benefits from this.'"
)

GUIDANCE_CONFIRMED = (
    "SHARPEN MODE STILL BINDING. "
    "Ask ONE question: 'What's the one constraint that limits this most — a deadline, limited hours, or a budget cap?' "
    "Then stop and wait. Do not suggest constraints.\n\n"
    "When user answers constraint → explain why all the questions were necessary and acknowledge the process then call frame_initiative_constraints with constraint_type + constraint_value."
)

# ============================================================================
# Tool Handler
# ============================================================================


async def handle(arguments: dict) -> mcp_types.CallToolResult:
    """Handle frame_initiative_intent tool call."""
    logger.debug("frame_initiative_intent.handle.start",
                argument_keys=list(arguments.keys()))

    # Pydantic validation
    try:
        validated_request = FrameIntentRequest.model_validate(arguments)
    except ValidationError as e:
        logger.warning("frame_initiative_intent.validation_failed", error=str(e.errors()))
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(type="text", text="Invalid input format.")],
            structuredContent={"error": "validation_error", "details": e.errors()},
            isError=True,
        )

    # Reject low/medium confidence
    if validated_request.confidence != "high":
        logger.info("frame_initiative_intent.confidence_rejected",
                   confidence=validated_request.confidence)
        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Confidence '{validated_request.confidence}' rejected. Only 'high' accepted.",
            )],
            structuredContent={
                "error": "confidence_too_low",
                "confidence_provided": validated_request.confidence,
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_CONFIDENCE_REJECTED,
                },
            },
            isError=True,
        )

    # Structural validation
    result = validate_initiative_intent(
        who=validated_request.who,
        what=validated_request.what,
        why=validated_request.why,
    )

    # If structurally invalid, return error
    if not result["valid"]:
        # Check for multiple stakeholders
        if result.get("multiple_stakeholders"):
            return mcp_types.CallToolResult(
                content=[mcp_types.TextContent(
                    type="text",
                    text="Multiple stakeholders detected. Need primary beneficiary.",
                )],
                structuredContent={
                    "error": "multiple_stakeholders",
                    "who_provided": result["framing_intent"]["who"],
                    "recovery_hint": "Ask user to name ONE primary beneficiary",
                    "assistant_guidance": {
                        "action": "ASK_CLARIFYING",
                        "instruction": GUIDANCE_MULTIPLE_STAKEHOLDERS,
                    },
                },
                isError=True,
            )

        return mcp_types.CallToolResult(
            content=[mcp_types.TextContent(
                type="text",
                text=f"Missing required fields: {', '.join(result['missing'])}",
            )],
            structuredContent={
                "error": "missing_fields",
                "missing": result["missing"],
                "assistant_guidance": {
                    "action": "ASK_CLARIFYING",
                    "instruction": GUIDANCE_MISSING_FIELDS,
                },
            },
            isError=True,
        )

    # Valid — return confirmed framing
    intent = result["framing_intent"]

    logger.info("frame_initiative_intent.complete",
               who=intent["who"], what=intent["what"], confidence="high")

    return mcp_types.CallToolResult(
        content=[mcp_types.TextContent(
            type="text",
            text=f"Intent confirmed: {intent['who']} needs {intent['what']} so that {intent['why']}",
        )],
        structuredContent={
            "framing_intent": intent,
            "confidence": "high",
            "confirmed": True,
            "assistant_guidance": {
                "action": "PROCEED_TO_CONSTRAINTS",
                "instruction": GUIDANCE_CONFIRMED,
            },
        },
    )


# ============================================================================
# Self-register at import time
# ============================================================================

register_tool(ToolDefinition(
    name="frame_initiative_intent",
    description=DESCRIPTION,
    input_schema=INPUT_SCHEMA,
    handle=handle,
    # OpenAI compliance annotations
    read_only_hint=False,  # Produces structured output for user
    destructive_hint=False,  # No data modification
    open_world_hint=False,  # No external API calls
))
