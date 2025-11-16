"""
Mixture-of-Agents Debate System

Implements multi-model debate for critical research decisions.
Multiple models independently analyze a question, then collaborate to reach consensus.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
from decimal import Decimal
import asyncio

from .registry import ModelInfo

logger = logging.getLogger(__name__)


class ConsensusStrategy(str, Enum):
    """Strategy for reaching consensus in debate"""
    MAJORITY_VOTE = "majority_vote"        # Simple majority voting
    WEIGHTED_CONFIDENCE = "weighted_confidence"  # Weight by confidence scores
    UNANIMOUS = "unanimous"                # Require unanimous agreement
    BEST_ARGUMENT = "best_argument"        # Select best-argued position


@dataclass
class DebateRound:
    """A single round of debate"""
    round_number: int
    question: str
    responses: Dict[str, Any] = field(default_factory=dict)  # model_id -> response
    confidence_scores: Dict[str, float] = field(default_factory=dict)  # model_id -> confidence
    agreements: Dict[str, List[str]] = field(default_factory=dict)  # position -> [model_ids]


@dataclass
class DebateResult:
    """Result of a multi-model debate"""
    consensus_reached: bool
    final_answer: Any
    confidence: float

    # Debate details
    rounds: List[DebateRound] = field(default_factory=list)
    models_participated: List[str] = field(default_factory=list)
    total_cost_usd: Decimal = Decimal("0.0")
    total_time_ms: float = 0.0

    # Agreement metrics
    agreement_level: float = 0.0  # 0.0 - 1.0
    dissenting_opinions: List[Dict[str, Any]] = field(default_factory=list)


class DebateCoordinator:
    """
    Coordinates mixture-of-agents debates.

    Process:
    1. Multiple models independently analyze question
    2. Models review each other's responses
    3. Models refine their positions
    4. Consensus reached via configured strategy
    """

    def __init__(
        self,
        max_rounds: int = 3,
        consensus_threshold: float = 0.75,
        min_confidence: float = 0.7
    ):
        self.max_rounds = max_rounds
        self.consensus_threshold = consensus_threshold
        self.min_confidence = min_confidence

    async def debate(
        self,
        question: str,
        models: List[ModelInfo],
        invoke_model_func: Any,  # Async function to invoke models
        strategy: ConsensusStrategy = ConsensusStrategy.WEIGHTED_CONFIDENCE,
        context: Optional[Dict[str, Any]] = None
    ) -> DebateResult:
        """
        Conduct multi-model debate.

        Args:
            question: Question to debate
            models: Models to participate
            invoke_model_func: Function to invoke models
            strategy: Consensus strategy
            context: Additional context

        Returns:
            DebateResult with consensus and metrics
        """
        import time

        start_time = time.time()
        rounds = []
        total_cost = Decimal("0.0")

        logger.info(
            f"Starting debate with {len(models)} models: "
            f"{[m.model_id for m in models]}"
        )

        # Round 1: Independent analysis
        round1 = await self._round_independent_analysis(
            question, models, invoke_model_func, context
        )
        rounds.append(round1)

        # Extract costs (if available in responses)
        for response in round1.responses.values():
            if isinstance(response, dict) and "cost" in response:
                total_cost += Decimal(str(response["cost"]))

        # Check for early consensus
        consensus, answer, confidence = self._check_consensus(
            round1, strategy
        )

        if consensus and confidence >= self.min_confidence:
            total_time = (time.time() - start_time) * 1000
            logger.info(
                f"Early consensus reached in round 1 "
                f"(confidence={confidence:.2f})"
            )
            return DebateResult(
                consensus_reached=True,
                final_answer=answer,
                confidence=confidence,
                rounds=rounds,
                models_participated=[m.model_id for m in models],
                total_cost_usd=total_cost,
                total_time_ms=total_time,
                agreement_level=self._calculate_agreement_level(round1)
            )

        # Round 2+: Collaborative refinement
        for round_num in range(2, self.max_rounds + 1):
            logger.info(f"Starting debate round {round_num}")

            # Models review and respond to each other
            round_n = await self._round_collaborative_refinement(
                question,
                models,
                rounds[-1],  # Previous round
                invoke_model_func,
                context
            )
            rounds.append(round_n)

            # Extract costs
            for response in round_n.responses.values():
                if isinstance(response, dict) and "cost" in response:
                    total_cost += Decimal(str(response["cost"]))

            # Check consensus
            consensus, answer, confidence = self._check_consensus(
                round_n, strategy
            )

            if consensus and confidence >= self.min_confidence:
                total_time = (time.time() - start_time) * 1000
                logger.info(
                    f"Consensus reached in round {round_num} "
                    f"(confidence={confidence:.2f})"
                )
                return DebateResult(
                    consensus_reached=True,
                    final_answer=answer,
                    confidence=confidence,
                    rounds=rounds,
                    models_participated=[m.model_id for m in models],
                    total_cost_usd=total_cost,
                    total_time_ms=total_time,
                    agreement_level=self._calculate_agreement_level(round_n)
                )

        # Max rounds reached without consensus
        total_time = (time.time() - start_time) * 1000

        # Use best available answer
        final_round = rounds[-1]
        _, best_answer, best_confidence = self._check_consensus(
            final_round, strategy
        )

        # Collect dissenting opinions
        dissenting = self._collect_dissenting_opinions(final_round, best_answer)

        logger.warning(
            f"No consensus after {self.max_rounds} rounds. "
            f"Using best answer with confidence={best_confidence:.2f}"
        )

        return DebateResult(
            consensus_reached=False,
            final_answer=best_answer,
            confidence=best_confidence,
            rounds=rounds,
            models_participated=[m.model_id for m in models],
            total_cost_usd=total_cost,
            total_time_ms=total_time,
            agreement_level=self._calculate_agreement_level(final_round),
            dissenting_opinions=dissenting
        )

    async def _round_independent_analysis(
        self,
        question: str,
        models: List[ModelInfo],
        invoke_model_func: Any,
        context: Optional[Dict[str, Any]]
    ) -> DebateRound:
        """Round 1: Each model independently analyzes the question"""

        prompt = self._build_independent_prompt(question, context)

        # Invoke all models concurrently
        tasks = [
            invoke_model_func(model.model_id, prompt, context or {})
            for model in models
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        round_data = DebateRound(
            round_number=1,
            question=question
        )

        for model, response in zip(models, responses):
            if isinstance(response, Exception):
                logger.error(
                    f"Model {model.model_id} failed in round 1: {response}"
                )
                continue

            # Extract answer and confidence
            if isinstance(response, dict):
                answer = response.get("answer", response)
                confidence = response.get("confidence", 0.5)
            else:
                answer = response
                confidence = 0.5

            round_data.responses[model.model_id] = answer
            round_data.confidence_scores[model.model_id] = confidence

        return round_data

    async def _round_collaborative_refinement(
        self,
        question: str,
        models: List[ModelInfo],
        previous_round: DebateRound,
        invoke_model_func: Any,
        context: Optional[Dict[str, Any]]
    ) -> DebateRound:
        """Subsequent rounds: Models review each other and refine"""

        prompt = self._build_refinement_prompt(
            question, previous_round, context
        )

        # Invoke all models concurrently
        tasks = [
            invoke_model_func(model.model_id, prompt, context or {})
            for model in models
        ]

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        round_data = DebateRound(
            round_number=previous_round.round_number + 1,
            question=question
        )

        for model, response in zip(models, responses):
            if isinstance(response, Exception):
                logger.error(
                    f"Model {model.model_id} failed in round {round_data.round_number}: {response}"
                )
                # Carry forward previous response
                if model.model_id in previous_round.responses:
                    round_data.responses[model.model_id] = previous_round.responses[model.model_id]
                    round_data.confidence_scores[model.model_id] = previous_round.confidence_scores.get(
                        model.model_id, 0.5
                    )
                continue

            # Extract refined answer and confidence
            if isinstance(response, dict):
                answer = response.get("answer", response)
                confidence = response.get("confidence", 0.5)
            else:
                answer = response
                confidence = 0.5

            round_data.responses[model.model_id] = answer
            round_data.confidence_scores[model.model_id] = confidence

        return round_data

    def _build_independent_prompt(
        self,
        question: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for independent analysis round"""
        prompt = f"""You are participating in a multi-agent debate to answer a research question.

Question: {question}

Please provide your analysis:
1. Your answer to the question
2. Your reasoning and evidence
3. Your confidence level (0.0 - 1.0)

"""
        if context:
            prompt += f"\nContext: {context}\n"

        prompt += """
Format your response as:
Answer: [your answer]
Reasoning: [your reasoning]
Confidence: [0.0-1.0]
"""

        return prompt

    def _build_refinement_prompt(
        self,
        question: str,
        previous_round: DebateRound,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build prompt for refinement round"""
        prompt = f"""You are participating in a multi-agent debate (Round {previous_round.round_number + 1}).

Question: {question}

Other agents' responses from previous round:
"""

        for model_id, response in previous_round.responses.items():
            confidence = previous_round.confidence_scores.get(model_id, 0.0)
            # Truncate long responses
            response_str = str(response)[:500]
            prompt += f"\nAgent {model_id} (confidence={confidence:.2f}):\n{response_str}\n"

        prompt += """
After reviewing other agents' responses:
1. Refine or confirm your answer
2. Explain if you changed your position and why
3. Update your confidence level

Format your response as:
Answer: [your refined answer]
Changes: [what changed and why]
Confidence: [0.0-1.0]
"""

        return prompt

    def _check_consensus(
        self,
        round_data: DebateRound,
        strategy: ConsensusStrategy
    ) -> tuple[bool, Any, float]:
        """
        Check if consensus has been reached.

        Returns:
            (consensus_reached, answer, confidence)
        """
        if not round_data.responses:
            return False, None, 0.0

        if strategy == ConsensusStrategy.MAJORITY_VOTE:
            return self._consensus_majority_vote(round_data)
        elif strategy == ConsensusStrategy.WEIGHTED_CONFIDENCE:
            return self._consensus_weighted_confidence(round_data)
        elif strategy == ConsensusStrategy.UNANIMOUS:
            return self._consensus_unanimous(round_data)
        elif strategy == ConsensusStrategy.BEST_ARGUMENT:
            return self._consensus_best_argument(round_data)
        else:
            return self._consensus_weighted_confidence(round_data)

    def _consensus_majority_vote(
        self,
        round_data: DebateRound
    ) -> tuple[bool, Any, float]:
        """Simple majority vote consensus"""
        # Group by answer (simplified: convert to string for comparison)
        answer_counts = {}
        for model_id, answer in round_data.responses.items():
            answer_str = str(answer).strip().lower()
            if answer_str not in answer_counts:
                answer_counts[answer_str] = {
                    "count": 0,
                    "models": [],
                    "original": answer
                }
            answer_counts[answer_str]["count"] += 1
            answer_counts[answer_str]["models"].append(model_id)

        if not answer_counts:
            return False, None, 0.0

        # Find majority
        total_votes = len(round_data.responses)
        majority_answer = max(answer_counts.items(), key=lambda x: x[1]["count"])

        majority_count = majority_answer[1]["count"]
        majority_pct = majority_count / total_votes

        if majority_pct >= self.consensus_threshold:
            # Average confidence of models that agreed
            agreeing_models = majority_answer[1]["models"]
            avg_confidence = sum(
                round_data.confidence_scores.get(m, 0.5)
                for m in agreeing_models
            ) / len(agreeing_models)

            return True, majority_answer[1]["original"], avg_confidence

        return False, majority_answer[1]["original"], majority_pct

    def _consensus_weighted_confidence(
        self,
        round_data: DebateRound
    ) -> tuple[bool, Any, float]:
        """Consensus weighted by confidence scores"""
        # Group by answer with confidence weights
        answer_weights = {}

        for model_id, answer in round_data.responses.items():
            answer_str = str(answer).strip().lower()
            confidence = round_data.confidence_scores.get(model_id, 0.5)

            if answer_str not in answer_weights:
                answer_weights[answer_str] = {
                    "weight": 0.0,
                    "models": [],
                    "original": answer
                }

            answer_weights[answer_str]["weight"] += confidence
            answer_weights[answer_str]["models"].append(model_id)

        if not answer_weights:
            return False, None, 0.0

        # Find answer with highest weighted score
        total_weight = sum(data["weight"] for data in answer_weights.values())
        best_answer = max(answer_weights.items(), key=lambda x: x[1]["weight"])

        best_weight = best_answer[1]["weight"]
        weight_pct = best_weight / total_weight if total_weight > 0 else 0.0

        # Average confidence of supporting models
        supporting_models = best_answer[1]["models"]
        avg_confidence = sum(
            round_data.confidence_scores.get(m, 0.5)
            for m in supporting_models
        ) / len(supporting_models)

        consensus_reached = weight_pct >= self.consensus_threshold

        return consensus_reached, best_answer[1]["original"], avg_confidence

    def _consensus_unanimous(
        self,
        round_data: DebateRound
    ) -> tuple[bool, Any, float]:
        """Require unanimous agreement"""
        if not round_data.responses:
            return False, None, 0.0

        # Check if all answers are the same (simplified)
        answers = [str(a).strip().lower() for a in round_data.responses.values()]
        unique_answers = set(answers)

        if len(unique_answers) == 1:
            # Unanimous!
            first_answer = list(round_data.responses.values())[0]
            avg_confidence = sum(round_data.confidence_scores.values()) / len(round_data.confidence_scores)
            return True, first_answer, avg_confidence

        # Not unanimous
        return False, list(round_data.responses.values())[0], 0.0

    def _consensus_best_argument(
        self,
        round_data: DebateRound
    ) -> tuple[bool, Any, float]:
        """Select answer with highest confidence"""
        if not round_data.confidence_scores:
            return False, None, 0.0

        best_model = max(
            round_data.confidence_scores.items(),
            key=lambda x: x[1]
        )

        model_id, confidence = best_model

        if confidence >= self.min_confidence:
            return True, round_data.responses[model_id], confidence

        return False, round_data.responses[model_id], confidence

    def _calculate_agreement_level(self, round_data: DebateRound) -> float:
        """Calculate overall agreement level (0.0 - 1.0)"""
        if not round_data.responses:
            return 0.0

        # Group answers
        answer_counts = {}
        for answer in round_data.responses.values():
            answer_str = str(answer).strip().lower()
            answer_counts[answer_str] = answer_counts.get(answer_str, 0) + 1

        # Calculate agreement as (largest group size / total responses)
        max_agreement = max(answer_counts.values())
        total = len(round_data.responses)

        return max_agreement / total

    def _collect_dissenting_opinions(
        self,
        round_data: DebateRound,
        consensus_answer: Any
    ) -> List[Dict[str, Any]]:
        """Collect opinions that differ from consensus"""
        consensus_str = str(consensus_answer).strip().lower()
        dissenting = []

        for model_id, answer in round_data.responses.items():
            answer_str = str(answer).strip().lower()
            if answer_str != consensus_str:
                dissenting.append({
                    "model_id": model_id,
                    "answer": answer,
                    "confidence": round_data.confidence_scores.get(model_id, 0.0)
                })

        return dissenting
