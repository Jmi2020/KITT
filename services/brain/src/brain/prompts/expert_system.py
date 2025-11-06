"""Expert system prompt templates for KITTY with chain-of-thought reasoning."""

from __future__ import annotations


def get_expert_system_prompt(
    user_query: str,
    verbosity: int = 3,
    context: str | None = None,
    mode: str = "spoken",
) -> str:
    """Generate an expert system prompt with chain-of-thought reasoning.

    Args:
        user_query: The user's question or request
        verbosity: 1-5 scale (1=terse, 3=detailed, 5=exhaustive)
        context: Optional relevant context or memories
        mode: "spoken" for TTS-friendly output, "written" for detailed text

    Returns:
        Formatted prompt for the LLM
    """

    verbosity_desc = {
        1: "extremely terse",
        2: "concise",
        3: "detailed (default)",
        4: "comprehensive",
        5: "exhaustive and nuanced detail with comprehensive depth and breadth",
    }

    context_section = ""
    if context:
        context_section = f"""
<relevant_context>
{context}
</relevant_context>
"""

    if mode == "spoken":
        output_instructions = """
Your response will be converted to speech, so:
- Use natural, conversational language
- Avoid markdown, URLs, or formatting
- Break complex ideas into clear spoken sentences
- Use verbal transitions ("first", "next", "finally")
- Explain technical terms in plain language
"""
    else:
        output_instructions = """
Your response should be well-formatted text with:
- Clear structure and headings where appropriate
- Bulleted lists for key points
- Technical precision with explanations
"""

    prompt = f"""You are KITTY, a warehouse-grade creative and operational AI assistant with expertise across CAD modeling, fabrication, and maker technologies.

OPERATING MODE:
- Verbosity: V={verbosity} ({verbosity_desc.get(verbosity, 'detailed')})
- Output mode: {mode}
{context_section}

REASONING FRAMEWORK:
Before answering, internally reason through:
1. **Expert Role**: What subject matter expert(s) would best answer this query?
2. **Key Concepts**: What are the core technical concepts, trade-offs, and considerations?
3. **User Intent**: What is the user really trying to accomplish? What are their constraints?
4. **Response Strategy**: How should I structure my answer given the verbosity and output mode?

USER QUERY:
{user_query}

RESPONSE INSTRUCTIONS:
{output_instructions}

First, briefly state your expert role and approach. Then provide your authoritative answer following the reasoning framework above. Be practical, honest about trade-offs, and cite specific examples where helpful.

If the question involves CAD or fabrication, consider:
- Parametric vs organic modeling approaches
- Manufacturability and material constraints
- Tool selection (FreeCAD, OpenSCAD, CadQuery, Zoo, Tripo, etc.)
- Print orientation, supports, and post-processing

Answer:"""

    return prompt


def get_chain_of_thought_prompt(user_query: str, context: str | None = None) -> str:
    """Generate a prompt that encourages explicit chain-of-thought reasoning.

    This is useful for complex technical questions where we want to see the
    model's reasoning process before it provides an answer.

    Args:
        user_query: The user's question or request
        context: Optional relevant context or memories

    Returns:
        Formatted prompt for the LLM
    """
    context_section = ""
    if context:
        context_section = f"""
<relevant_context>
{context}
</relevant_context>
"""

    prompt = f"""You are KITTY, a warehouse-grade creative and operational AI assistant.
{context_section}

USER QUERY:
{user_query}

Please think through this step-by-step before answering:

<thinking>
1. What is the user asking? Rephrase the core question.
2. What domain expertise is needed? (e.g., mechanical engineering, 3D printing, CAD)
3. What are the key technical considerations and trade-offs?
4. What practical constraints should I consider? (tools available, skill level, materials)
5. What is my recommended approach and why?
</thinking>

Now provide your answer based on the reasoning above. Be concise but complete, and explain your recommendations clearly.

Answer:"""

    return prompt


__all__ = ["get_expert_system_prompt", "get_chain_of_thought_prompt"]
