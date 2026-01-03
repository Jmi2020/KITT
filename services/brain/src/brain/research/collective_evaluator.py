"""
Collective Evaluation Protocol for Dataset Generation

Implements multi-agent evaluation for extracted claims and dataset entries.
Uses multiple LLM agents to evaluate accuracy, novelty, and coherence.

Evaluation Dimensions:
- Accuracy: Factual correctness and evidence support
- Novelty: Non-redundant, adds new information
- Coherence: Clear, well-structured, internally consistent

Decision Thresholds:
- ACCEPT: Score >= 0.75 (include in dataset)
- REFINE: Score 0.4-0.75 (needs improvement)
- REJECT: Score < 0.4 (exclude from dataset)
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import uuid

import httpx

from .extraction_schemas import (
    ExtractedClaim,
    DatasetEntry,
    EvaluationDecision,
    ClaimType,
)

logger = logging.getLogger(__name__)

# Token limits (leave room for prompt overhead)
MAX_BATCH_TOKENS = 28000


class EvaluationDimension(str, Enum):
    """Dimensions for multi-agent evaluation."""
    ACCURACY = "accuracy"
    NOVELTY = "novelty"
    COHERENCE = "coherence"


@dataclass
class AgentEvaluation:
    """Evaluation result from a single agent."""
    agent_id: str
    dimension: EvaluationDimension
    score: float  # 0-1
    reasoning: str
    issues_found: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)


@dataclass
class CollectiveEvaluationResult:
    """Combined result from all evaluation agents."""
    item_id: str  # claim_id or entry_id
    item_type: str  # "claim" or "entry"
    decision: EvaluationDecision
    overall_score: float
    dimension_scores: Dict[str, float]
    agent_evaluations: List[AgentEvaluation]
    consensus_reasoning: str
    refinement_suggestions: List[str]
    evaluated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class BatchEvaluationResult:
    """Result from evaluating a batch of items."""
    batch_id: str
    items_evaluated: int
    accepted: int
    refined: int
    rejected: int
    results: List[CollectiveEvaluationResult]
    total_tokens_used: int
    duration_seconds: float


# Evaluation prompts for each dimension
ACCURACY_PROMPT = """You are an accuracy evaluator for research claims.

Evaluate the following claim for FACTUAL ACCURACY:
- Is the claim supported by the provided evidence quotes?
- Are there any factual errors or misrepresentations?
- Is the claim consistent with established scientific knowledge?

CLAIM:
{claim_text}

EVIDENCE QUOTES:
{evidence_quotes}

SOURCE PAPER: {paper_title}

Respond in JSON format:
```json
{{
  "score": <0.0-1.0>,
  "reasoning": "<explanation of your evaluation>",
  "issues_found": ["<list of accuracy issues>"],
  "suggestions": ["<suggestions for improvement>"]
}}
```"""

NOVELTY_PROMPT = """You are a novelty evaluator for research claims.

Evaluate the following claim for NOVELTY and non-redundancy:
- Does this claim provide new, non-obvious information?
- Is it redundant with common knowledge?
- Does it add value beyond what's already well-established?

CLAIM:
{claim_text}

CLAIM TYPE: {claim_type}

RELATED CLAIMS (for context):
{related_claims}

Respond in JSON format:
```json
{{
  "score": <0.0-1.0>,
  "reasoning": "<explanation of your evaluation>",
  "issues_found": ["<list of novelty issues>"],
  "suggestions": ["<suggestions for improvement>"]
}}
```"""

COHERENCE_PROMPT = """You are a coherence evaluator for research claims.

Evaluate the following claim for CLARITY and COHERENCE:
- Is the claim clearly and precisely stated?
- Is it internally consistent?
- Is it well-structured for use in a training dataset?

CLAIM:
{claim_text}

CLAIM TYPE: {claim_type}
SECTION: {section}

Respond in JSON format:
```json
{{
  "score": <0.0-1.0>,
  "reasoning": "<explanation of your evaluation>",
  "issues_found": ["<list of coherence issues>"],
  "suggestions": ["<suggestions for improvement>"]
}}
```"""

ENTRY_EVALUATION_PROMPT = """You are evaluating a training dataset entry for quality.

Evaluate this instruction-output pair for:
1. ACCURACY: Is the output factually correct?
2. HELPFULNESS: Does it properly answer the instruction?
3. COHERENCE: Is it well-written and clear?
4. COMPLETENESS: Does it fully address the instruction?

INSTRUCTION:
{instruction}

INPUT (context):
{input}

OUTPUT:
{output}

Respond in JSON format:
```json
{{
  "accuracy_score": <0.0-1.0>,
  "helpfulness_score": <0.0-1.0>,
  "coherence_score": <0.0-1.0>,
  "completeness_score": <0.0-1.0>,
  "overall_score": <0.0-1.0>,
  "reasoning": "<explanation>",
  "issues": ["<list of issues>"],
  "suggestions": ["<suggestions>"]
}}
```"""


class CollectiveEvaluator:
    """
    Multi-agent evaluator for research claims and dataset entries.

    Uses multiple evaluation dimensions with consensus scoring.
    """

    # Decision thresholds
    ACCEPT_THRESHOLD = 0.75
    REFINE_THRESHOLD = 0.40

    def __init__(
        self,
        q4_url: str = "http://localhost:8083/v1/chat/completions",
        ollama_url: str = "http://localhost:11434/api/generate",
        timeout: float = 120.0,
    ):
        self.q4_url = q4_url
        self.ollama_url = ollama_url
        self.timeout = timeout

    async def evaluate_claim(
        self,
        claim: ExtractedClaim,
        related_claims: Optional[List[ExtractedClaim]] = None,
        paper_title: str = "",
    ) -> CollectiveEvaluationResult:
        """
        Evaluate a single claim using multi-agent consensus.

        Args:
            claim: The claim to evaluate
            related_claims: Related claims for novelty comparison
            paper_title: Title of the source paper

        Returns:
            CollectiveEvaluationResult with decision and scores
        """
        agent_evaluations = []

        # Run evaluation agents in parallel
        tasks = [
            self._evaluate_accuracy(claim, paper_title),
            self._evaluate_novelty(claim, related_claims or []),
            self._evaluate_coherence(claim),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, AgentEvaluation):
                agent_evaluations.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Evaluation agent failed: {result}")

        # Calculate aggregate scores
        dimension_scores = {}
        for eval in agent_evaluations:
            dimension_scores[eval.dimension.value] = eval.score

        # Overall score is weighted average
        weights = {
            EvaluationDimension.ACCURACY.value: 0.5,
            EvaluationDimension.NOVELTY.value: 0.25,
            EvaluationDimension.COHERENCE.value: 0.25,
        }

        overall_score = 0.0
        total_weight = 0.0
        for dim, score in dimension_scores.items():
            weight = weights.get(dim, 0.25)
            overall_score += score * weight
            total_weight += weight

        if total_weight > 0:
            overall_score /= total_weight

        # Make decision
        if overall_score >= self.ACCEPT_THRESHOLD:
            decision = EvaluationDecision.ACCEPT
        elif overall_score >= self.REFINE_THRESHOLD:
            decision = EvaluationDecision.REFINE
        else:
            decision = EvaluationDecision.REJECT

        # Collect suggestions
        all_suggestions = []
        for eval in agent_evaluations:
            all_suggestions.extend(eval.suggestions)

        # Generate consensus reasoning
        consensus = self._generate_consensus(agent_evaluations, overall_score, decision)

        return CollectiveEvaluationResult(
            item_id=claim.id,
            item_type="claim",
            decision=decision,
            overall_score=round(overall_score, 3),
            dimension_scores=dimension_scores,
            agent_evaluations=agent_evaluations,
            consensus_reasoning=consensus,
            refinement_suggestions=all_suggestions[:5],  # Top 5 suggestions
        )

    async def evaluate_entry(
        self,
        entry: DatasetEntry,
    ) -> CollectiveEvaluationResult:
        """
        Evaluate a dataset entry for training quality.

        Args:
            entry: The dataset entry to evaluate

        Returns:
            CollectiveEvaluationResult with decision and scores
        """
        prompt = ENTRY_EVALUATION_PROMPT.format(
            instruction=entry.instruction,
            input=entry.input or "(none)",
            output=entry.output,
        )

        response = await self._call_llm(prompt)

        try:
            result = self._parse_json_response(response)

            dimension_scores = {
                "accuracy": result.get("accuracy_score", 0.5),
                "helpfulness": result.get("helpfulness_score", 0.5),
                "coherence": result.get("coherence_score", 0.5),
                "completeness": result.get("completeness_score", 0.5),
            }

            overall_score = result.get(
                "overall_score",
                sum(dimension_scores.values()) / len(dimension_scores)
            )

            # Make decision
            if overall_score >= self.ACCEPT_THRESHOLD:
                decision = EvaluationDecision.ACCEPT
            elif overall_score >= self.REFINE_THRESHOLD:
                decision = EvaluationDecision.REFINE
            else:
                decision = EvaluationDecision.REJECT

            agent_eval = AgentEvaluation(
                agent_id="entry_evaluator",
                dimension=EvaluationDimension.ACCURACY,
                score=overall_score,
                reasoning=result.get("reasoning", ""),
                issues_found=result.get("issues", []),
                suggestions=result.get("suggestions", []),
            )

            return CollectiveEvaluationResult(
                item_id=entry.id,
                item_type="entry",
                decision=decision,
                overall_score=round(overall_score, 3),
                dimension_scores=dimension_scores,
                agent_evaluations=[agent_eval],
                consensus_reasoning=result.get("reasoning", ""),
                refinement_suggestions=result.get("suggestions", [])[:5],
            )

        except Exception as e:
            logger.error(f"Failed to parse entry evaluation: {e}")
            return CollectiveEvaluationResult(
                item_id=entry.id,
                item_type="entry",
                decision=EvaluationDecision.REFINE,
                overall_score=0.5,
                dimension_scores={},
                agent_evaluations=[],
                consensus_reasoning=f"Evaluation failed: {e}",
                refinement_suggestions=[],
            )

    async def evaluate_batch(
        self,
        claims: List[ExtractedClaim],
        budget: int = MAX_BATCH_TOKENS,
        external_calls: int = 3,
    ) -> BatchEvaluationResult:
        """
        Evaluate a batch of claims with token budget.

        Args:
            claims: List of claims to evaluate
            budget: Maximum tokens to use
            external_calls: Maximum LLM calls for this batch

        Returns:
            BatchEvaluationResult with all evaluations
        """
        batch_id = uuid.uuid4().hex[:8]
        start_time = datetime.utcnow()

        results: List[CollectiveEvaluationResult] = []
        tokens_used = 0
        calls_made = 0

        for claim in claims:
            if calls_made >= external_calls:
                logger.info(f"Batch {batch_id}: Reached call limit ({external_calls})")
                break

            try:
                result = await self.evaluate_claim(claim)
                results.append(result)
                calls_made += 3  # 3 agents per claim
                tokens_used += 2000  # Estimate
            except Exception as e:
                logger.error(f"Failed to evaluate claim {claim.id}: {e}")

        # Count decisions
        accepted = sum(1 for r in results if r.decision == EvaluationDecision.ACCEPT)
        refined = sum(1 for r in results if r.decision == EvaluationDecision.REFINE)
        rejected = sum(1 for r in results if r.decision == EvaluationDecision.REJECT)

        duration = (datetime.utcnow() - start_time).total_seconds()

        return BatchEvaluationResult(
            batch_id=batch_id,
            items_evaluated=len(results),
            accepted=accepted,
            refined=refined,
            rejected=rejected,
            results=results,
            total_tokens_used=tokens_used,
            duration_seconds=round(duration, 2),
        )

    async def _evaluate_accuracy(
        self,
        claim: ExtractedClaim,
        paper_title: str,
    ) -> AgentEvaluation:
        """Run accuracy evaluation agent."""
        evidence_quotes = "\n".join(
            f"- \"{q.quote}\"" for q in claim.evidence_quotes[:5]
        )

        prompt = ACCURACY_PROMPT.format(
            claim_text=claim.claim_text,
            evidence_quotes=evidence_quotes or "(no quotes available)",
            paper_title=paper_title or "(unknown)",
        )

        response = await self._call_llm(prompt)
        result = self._parse_json_response(response)

        return AgentEvaluation(
            agent_id="accuracy_agent",
            dimension=EvaluationDimension.ACCURACY,
            score=float(result.get("score", 0.5)),
            reasoning=result.get("reasoning", ""),
            issues_found=result.get("issues_found", []),
            suggestions=result.get("suggestions", []),
        )

    async def _evaluate_novelty(
        self,
        claim: ExtractedClaim,
        related_claims: List[ExtractedClaim],
    ) -> AgentEvaluation:
        """Run novelty evaluation agent."""
        related_text = "\n".join(
            f"- {c.claim_text}" for c in related_claims[:5]
        ) if related_claims else "(no related claims)"

        prompt = NOVELTY_PROMPT.format(
            claim_text=claim.claim_text,
            claim_type=claim.claim_type.value,
            related_claims=related_text,
        )

        response = await self._call_llm(prompt)
        result = self._parse_json_response(response)

        return AgentEvaluation(
            agent_id="novelty_agent",
            dimension=EvaluationDimension.NOVELTY,
            score=float(result.get("score", 0.5)),
            reasoning=result.get("reasoning", ""),
            issues_found=result.get("issues_found", []),
            suggestions=result.get("suggestions", []),
        )

    async def _evaluate_coherence(
        self,
        claim: ExtractedClaim,
    ) -> AgentEvaluation:
        """Run coherence evaluation agent."""
        prompt = COHERENCE_PROMPT.format(
            claim_text=claim.claim_text,
            claim_type=claim.claim_type.value,
            section=claim.section.value,
        )

        response = await self._call_llm(prompt)
        result = self._parse_json_response(response)

        return AgentEvaluation(
            agent_id="coherence_agent",
            dimension=EvaluationDimension.COHERENCE,
            score=float(result.get("score", 0.5)),
            reasoning=result.get("reasoning", ""),
            issues_found=result.get("issues_found", []),
            suggestions=result.get("suggestions", []),
        )

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM via llama.cpp Q4 server."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.q4_url,
                    json={
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.1,
                        "max_tokens": 1000,
                        "stream": False,
                    }
                )
                response.raise_for_status()
                data = response.json()

                if "choices" in data and data["choices"]:
                    return data["choices"][0].get("message", {}).get("content", "")

                return ""

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return "{}"

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response."""
        if not response:
            return {"score": 0.5}

        # Try to extract JSON from response
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # Try to find JSON directly
            start = response.find('{')
            end = response.rfind('}')
            if start != -1 and end != -1:
                json_str = response[start:end + 1]
            else:
                return {"score": 0.5}

        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse JSON: {json_str[:100]}")
            return {"score": 0.5}

    def _generate_consensus(
        self,
        evaluations: List[AgentEvaluation],
        overall_score: float,
        decision: EvaluationDecision,
    ) -> str:
        """Generate consensus reasoning from agent evaluations."""
        parts = [f"Overall score: {overall_score:.2f} ({decision.value})"]

        for eval in evaluations:
            parts.append(
                f"{eval.dimension.value.title()}: {eval.score:.2f} - {eval.reasoning[:100]}"
            )

        return " | ".join(parts)


# Global instance
_evaluator: Optional[CollectiveEvaluator] = None


def get_collective_evaluator() -> CollectiveEvaluator:
    """Get or create the global collective evaluator."""
    global _evaluator
    if _evaluator is None:
        _evaluator = CollectiveEvaluator()
    return _evaluator
