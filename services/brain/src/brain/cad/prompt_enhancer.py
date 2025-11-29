"""Zoo prompt enhancement for text-to-CAD generation.

Analyzes user CAD prompts for completeness, generates clarifying questions
for missing critical dimensions, and formats prompts to meet Zoo guidelines.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..llm_client import chat_async
from .prompt_templates import (
    ANALYSIS_SYSTEM_PROMPT,
    ANALYSIS_USER_PROMPT,
    CONFIRMATION_TEMPLATE,
    ENHANCE_SYSTEM_PROMPT,
    ENHANCE_USER_PROMPT,
    QUESTIONS_SYSTEM_PROMPT,
    QUESTIONS_USER_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class PromptAnalysis:
    """Result of analyzing a CAD prompt for completeness."""

    part_type: Optional[str] = None
    part_type_inferred: Optional[str] = None
    has_dimensions: bool = False
    dimensions_found: Optional[Dict[str, str]] = None
    has_fasteners: bool = False
    fasteners_found: Optional[Dict[str, Any]] = None
    missing_critical: List[str] = field(default_factory=list)
    can_infer: List[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: Optional[str] = None

    @property
    def is_complete(self) -> bool:
        """Check if prompt has all critical information."""
        return len(self.missing_critical) == 0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PromptAnalysis":
        """Create from LLM response dict."""
        return cls(
            part_type=data.get("part_type"),
            part_type_inferred=data.get("part_type_inferred"),
            has_dimensions=data.get("has_dimensions", False),
            dimensions_found=data.get("dimensions_found"),
            has_fasteners=data.get("has_fasteners", False),
            fasteners_found=data.get("fasteners_found"),
            missing_critical=data.get("missing_critical", []),
            can_infer=data.get("can_infer", []),
            confidence=data.get("confidence", 0.0),
            notes=data.get("notes"),
        )


@dataclass
class ClarifyingQuestion:
    """A question to ask the user for missing information."""

    field: str
    question: str
    example: Optional[str] = None


class ZooPromptEnhancer:
    """Enhances user CAD prompts to meet Zoo text-to-CAD guidelines.

    The enhancer follows a hybrid approach:
    1. Analyze prompt for completeness
    2. Ask user for missing critical dimensions (overall size, fasteners)
    3. Auto-infer non-critical details (fillets, material)
    4. Format to Zoo's 1-2 sentence guideline
    5. Show enhanced prompt to user for confirmation
    """

    # Critical fields that require user input if missing
    CRITICAL_FIELDS = {"dimensions", "fastener_specs", "part_type"}

    # Non-critical fields that can use reasonable defaults
    INFERRABLE_FIELDS = {"fillet_radius", "chamfer_size", "material", "edge_treatment"}

    def __init__(self, model_tier: str = "Q4"):
        """Initialize the enhancer.

        Args:
            model_tier: Which local model tier to use (Q4, F16, etc.)
        """
        self.model_tier = model_tier

    async def analyze_prompt(self, prompt: str) -> PromptAnalysis:
        """Analyze a CAD prompt for completeness against Zoo guidelines.

        Args:
            prompt: User's original CAD request

        Returns:
            PromptAnalysis with assessment of what's present/missing
        """
        messages = [
            {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
            {"role": "user", "content": ANALYSIS_USER_PROMPT.format(prompt=prompt)},
        ]

        try:
            response, _metadata = await chat_async(
                messages=messages,
                which=self.model_tier,
                temperature=0.1,  # Low temperature for consistent analysis
                max_tokens=500,
            )

            # Parse JSON from response
            analysis_data = self._extract_json(response)
            if analysis_data:
                return PromptAnalysis.from_dict(analysis_data)

            logger.warning("Failed to parse analysis JSON, returning default")
            return PromptAnalysis(missing_critical=["dimensions", "part_type"])

        except Exception as e:
            logger.error(f"Error analyzing prompt: {e}")
            # Return conservative analysis on error
            return PromptAnalysis(
                missing_critical=["dimensions"],
                notes=f"Analysis error: {e}",
            )

    async def generate_questions(
        self, prompt: str, analysis: PromptAnalysis
    ) -> List[ClarifyingQuestion]:
        """Generate clarifying questions for missing critical information.

        Args:
            prompt: Original user prompt
            analysis: Result from analyze_prompt()

        Returns:
            List of questions to ask the user
        """
        if not analysis.missing_critical:
            return []

        messages = [
            {"role": "system", "content": QUESTIONS_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": QUESTIONS_USER_PROMPT.format(
                    prompt=prompt,
                    missing_critical=json.dumps(analysis.missing_critical),
                    part_type=analysis.part_type or analysis.part_type_inferred or "unknown",
                ),
            },
        ]

        try:
            response, _metadata = await chat_async(
                messages=messages,
                which=self.model_tier,
                temperature=0.3,
                max_tokens=400,
            )

            questions_data = self._extract_json(response)
            if questions_data and isinstance(questions_data, list):
                return [
                    ClarifyingQuestion(
                        field=q.get("field", "unknown"),
                        question=q.get("question", ""),
                        example=q.get("example"),
                    )
                    for q in questions_data
                ]

            # Fallback: generate simple questions based on missing fields
            return self._fallback_questions(analysis.missing_critical)

        except Exception as e:
            logger.error(f"Error generating questions: {e}")
            return self._fallback_questions(analysis.missing_critical)

    async def enhance_prompt(
        self,
        prompt: str,
        user_answers: Optional[Dict[str, str]] = None,
        analysis: Optional[PromptAnalysis] = None,
    ) -> str:
        """Format prompt to Zoo guidelines (1-2 concise sentences).

        Args:
            prompt: Original user prompt
            user_answers: Answers to clarifying questions (if any were asked)
            analysis: Previous analysis result (optional, will analyze if not provided)

        Returns:
            Enhanced prompt formatted for Zoo API
        """
        # Build additional context from user answers
        additional_context = ""
        if user_answers:
            additional_context = "User provided additional details:\n"
            for field, answer in user_answers.items():
                additional_context += f"- {field}: {answer}\n"

        messages = [
            {"role": "system", "content": ENHANCE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": ENHANCE_USER_PROMPT.format(
                    prompt=prompt,
                    additional_context=additional_context,
                ),
            },
        ]

        try:
            response, _metadata = await chat_async(
                messages=messages,
                which=self.model_tier,
                temperature=0.2,  # Low temp for consistent formatting
                max_tokens=300,
            )

            # Clean up response - should be just the enhanced prompt
            enhanced = response.strip()

            # Remove any markdown formatting or quotes
            enhanced = re.sub(r'^["\']|["\']$', "", enhanced)
            enhanced = re.sub(r"^```.*\n?|```$", "", enhanced, flags=re.MULTILINE)

            # Ensure it's not too long (Zoo prefers short prompts)
            if len(enhanced) > 500:
                logger.warning(f"Enhanced prompt too long ({len(enhanced)} chars), truncating")
                # Try to truncate at sentence boundary
                sentences = enhanced.split(". ")
                enhanced = ". ".join(sentences[:2]) + "."

            return enhanced.strip()

        except Exception as e:
            logger.error(f"Error enhancing prompt: {e}")
            # Return original prompt on error
            return prompt

    def format_confirmation(self, enhanced_prompt: str) -> str:
        """Format the enhanced prompt for user confirmation.

        Args:
            enhanced_prompt: The enhanced prompt to confirm

        Returns:
            Formatted message asking for user confirmation
        """
        return CONFIRMATION_TEMPLATE.format(enhanced_prompt=enhanced_prompt)

    def _extract_json(self, text: str) -> Optional[Any]:
        """Extract JSON from LLM response text.

        Args:
            text: Raw LLM response that may contain JSON

        Returns:
            Parsed JSON object or None if extraction fails
        """
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Look for JSON in code blocks
        code_block_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block_match:
            try:
                return json.loads(code_block_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Look for JSON object/array anywhere in text
        json_match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", text)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def _fallback_questions(self, missing_fields: List[str]) -> List[ClarifyingQuestion]:
        """Generate simple fallback questions for missing fields."""
        questions = []

        field_questions = {
            "dimensions": ClarifyingQuestion(
                field="dimensions",
                question="What are the overall dimensions? (length × width × height in mm)",
                example="For example: 100×50×5 mm",
            ),
            "fastener_specs": ClarifyingQuestion(
                field="fastener_specs",
                question="What fastener/hole specifications do you need? (size, count, pattern)",
                example="For example: four M6 holes at corners, or two 8mm holes 15mm from edges",
            ),
            "part_type": ClarifyingQuestion(
                field="part_type",
                question="What type of part is this? (bracket, plate, flange, spacer, etc.)",
                example="For example: mounting bracket, adapter plate, spacer ring",
            ),
        }

        for field in missing_fields:
            if field in field_questions:
                questions.append(field_questions[field])

        return questions


async def process_cad_prompt(
    prompt: str,
    user_answers: Optional[Dict[str, str]] = None,
    skip_confirmation: bool = False,
) -> Dict[str, Any]:
    """Main entry point for CAD prompt processing.

    This function orchestrates the full enhancement flow:
    1. Analyze prompt for completeness
    2. If missing critical info, return questions to ask
    3. If complete (or answers provided), enhance and return formatted prompt

    Args:
        prompt: User's original CAD request
        user_answers: Answers to previously asked questions (if any)
        skip_confirmation: If True, don't return confirmation message

    Returns:
        Dict with one of:
        - {"needs_clarification": True, "questions": [...], "analysis": {...}}
        - {"enhanced_prompt": "...", "confirmation_message": "...", "analysis": {...}}
    """
    enhancer = ZooPromptEnhancer()

    # Analyze the prompt
    analysis = await enhancer.analyze_prompt(prompt)

    logger.info(
        f"CAD prompt analysis: complete={analysis.is_complete}, "
        f"missing={analysis.missing_critical}, confidence={analysis.confidence}"
    )

    # If user provided answers, we can skip straight to enhancement
    if user_answers:
        enhanced = await enhancer.enhance_prompt(prompt, user_answers, analysis)
        result = {
            "enhanced_prompt": enhanced,
            "analysis": {
                "part_type": analysis.part_type,
                "confidence": analysis.confidence,
            },
        }
        if not skip_confirmation:
            result["confirmation_message"] = enhancer.format_confirmation(enhanced)
        return result

    # Check if we need clarification
    if not analysis.is_complete:
        questions = await enhancer.generate_questions(prompt, analysis)
        return {
            "needs_clarification": True,
            "questions": [
                {
                    "field": q.field,
                    "question": q.question,
                    "example": q.example,
                }
                for q in questions
            ],
            "analysis": {
                "part_type": analysis.part_type or analysis.part_type_inferred,
                "missing": analysis.missing_critical,
            },
        }

    # Prompt is complete enough - enhance it
    enhanced = await enhancer.enhance_prompt(prompt, analysis=analysis)
    result = {
        "enhanced_prompt": enhanced,
        "analysis": {
            "part_type": analysis.part_type,
            "confidence": analysis.confidence,
        },
    }
    if not skip_confirmation:
        result["confirmation_message"] = enhancer.format_confirmation(enhanced)

    return result
