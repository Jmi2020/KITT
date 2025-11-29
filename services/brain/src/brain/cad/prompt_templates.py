"""LLM prompt templates for Zoo CAD prompt enhancement.

Based on Zoo's text-to-CAD guidelines:
- Concise: 1-2 well-structured sentences
- Structured: overall part → dimensions → features → relationships
- Quantitative: concrete numbers and units (mm, in)
- Deterministic: no ambiguous words like "about", "roughly"
- Mechanically oriented: mechanical parts and clear operations
- Single intent: one part at a time
"""

# System prompt for analyzing CAD prompt completeness
ANALYSIS_SYSTEM_PROMPT = """You are analyzing a CAD design request for completeness against Zoo's text-to-CAD guidelines.

CRITICAL elements that MUST be specified by the user (ask if missing):
1. Part type (bracket, plate, flange, spacer, adapter, gear, etc.)
2. Overall dimensions (L×W×H in mm, or diameter×height for cylindrical)
3. Fastener/hole specifications (if applicable): size, count, pattern

NON-CRITICAL elements that can be inferred with reasonable defaults:
- Fillet/chamfer radius (default: 2-3mm)
- Material (default: aluminum or steel)
- Wall thickness for hollow parts (default: 3-5mm based on size)
- Edge treatments (default: break sharp edges)

Analyze the user's request and return a JSON object with your assessment."""

ANALYSIS_USER_PROMPT = """Analyze this CAD design request:

"{prompt}"

Return JSON with this exact structure:
{{
  "part_type": "bracket" | "plate" | "flange" | "gear" | "spacer" | "adapter" | "housing" | "mount" | "custom" | null,
  "part_type_inferred": "description if inferred from context" | null,
  "has_dimensions": true | false,
  "dimensions_found": {{"length": "100mm", "width": "50mm", "height": "5mm"}} | null,
  "has_fasteners": true | false | "not_applicable",
  "fasteners_found": {{"type": "M8", "count": 4, "pattern": "corners"}} | null,
  "missing_critical": ["dimensions", "fastener_specs"],
  "can_infer": ["fillet_radius", "material"],
  "confidence": 0.0 to 1.0,
  "notes": "any relevant observations about the request"
}}

Only include fields in missing_critical if they are truly missing AND needed for this part type.
For example, a solid spacer may not need fastener specs."""

# System prompt for generating clarifying questions
QUESTIONS_SYSTEM_PROMPT = """You are helping a user specify their CAD design request.
Generate clear, friendly questions to gather missing critical information.

Keep questions:
- Specific and actionable
- Focused on what's actually needed
- Conversational but efficient
- Include example values where helpful

Do NOT ask about:
- Non-critical details like fillet radius
- Material unless structurally important
- Aesthetic preferences"""

QUESTIONS_USER_PROMPT = """Based on this analysis of a CAD request:

Original request: "{prompt}"
Missing critical info: {missing_critical}
Part type: {part_type}

Generate 1-3 clarifying questions to get the missing information.
Return JSON array:
[
  {{
    "field": "dimensions",
    "question": "What are the overall dimensions? (e.g., 100×50×5 mm)",
    "example": "For a mounting bracket, typical sizes are 50-200mm length"
  }}
]"""

# System prompt for enhancing/formatting the final prompt
ENHANCE_SYSTEM_PROMPT = """You are formatting a CAD design request for Zoo's text-to-CAD API.

STRICT GUIDELINES:
1. Output exactly 1-2 concise sentences
2. Structure: part type → overall shape → dimensions → holes/features → edge treatments
3. Use exact numbers with units (mm preferred)
4. No ambiguous words: "about", "roughly", "approximately"
5. No stories or context - just mechanical specifications

TEMPLATE STRUCTURE:
"A [part_type] [shape], [L×W×H] mm, with [hole_specs] [hole_pattern], [features] [edge_treatment]."

EXAMPLE OUTPUT:
"An L-shaped steel bracket, 100×50×5 mm, with two 8mm through-holes on the long leg centered 15mm from edges, filleted 3mm on all external corners."

DEFAULTS TO APPLY when not specified:
- Fillet radius: 2mm on external corners
- Chamfer: 1mm on edges if no fillet
- Hole edge distance: 1.5× hole diameter from edges
- Counterbore depth: 0.5× bolt head height"""

ENHANCE_USER_PROMPT = """Format this CAD request for Zoo's text-to-CAD API:

Original request: "{prompt}"
{additional_context}

Apply defaults for unspecified non-critical details.
Output ONLY the formatted prompt (1-2 sentences), nothing else."""

# Template for presenting enhanced prompt to user for confirmation
CONFIRMATION_TEMPLATE = """I'll send this to Zoo for CAD generation:

> {enhanced_prompt}

Does this look correct? You can say:
- "Yes" to proceed
- Or describe any changes needed"""
