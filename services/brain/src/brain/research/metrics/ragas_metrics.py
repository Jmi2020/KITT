"""
RAGAS Quality Metrics Integration

Integrates RAGAS (Retrieval Augmented Generation Assessment) framework
for evaluating research output quality.

Key Metrics:
- Faithfulness: How grounded is the answer in retrieved context?
- Answer Relevancy: How relevant is the answer to the question?
- Context Precision: How precise is the retrieved context?
- Context Recall: How much of the ground truth is captured?
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class RAGASMetrics:
    """RAGAS metric scores"""
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0

    def average(self) -> float:
        """Calculate average of all metrics"""
        metrics = [
            self.faithfulness,
            self.answer_relevancy,
            self.context_precision,
            self.context_recall
        ]
        return sum(metrics) / len(metrics)

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            "faithfulness": self.faithfulness,
            "answer_relevancy": self.answer_relevancy,
            "context_precision": self.context_recall,
            "context_recall": self.context_recall,
            "average": self.average()
        }


@dataclass
class RAGASResult:
    """Result of RAGAS evaluation"""
    metrics: RAGASMetrics
    success: bool
    error: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class RAGASEvaluator:
    """
    Evaluates research outputs using RAGAS framework.

    Note: This is a simplified implementation for Phase 4.
    Full RAGAS integration requires the ragas library and embedding models.
    For now, we use heuristic-based approximations.
    """

    def __init__(
        self,
        use_full_ragas: bool = False,
        min_faithfulness: float = 0.7,
        min_relevancy: float = 0.7
    ):
        """
        Initialize RAGAS evaluator.

        Args:
            use_full_ragas: If True, use actual RAGAS library (requires setup)
            min_faithfulness: Minimum acceptable faithfulness score
            min_relevancy: Minimum acceptable relevancy score
        """
        self.use_full_ragas = use_full_ragas
        self.min_faithfulness = min_faithfulness
        self.min_relevancy = min_relevancy

        if use_full_ragas:
            try:
                # Try importing RAGAS
                from ragas import evaluate
                from ragas.metrics import (
                    faithfulness,
                    answer_relevancy,
                    context_precision,
                    context_recall
                )
                self.ragas_available = True
                logger.info("RAGAS library loaded successfully")
            except ImportError:
                logger.warning(
                    "RAGAS library not available, using heuristic approximations"
                )
                self.ragas_available = False
        else:
            self.ragas_available = False
            logger.info("Using heuristic-based quality metrics")

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str] = None
    ) -> RAGASResult:
        """
        Evaluate answer quality using RAGAS metrics.

        Args:
            question: The research question
            answer: The generated answer
            contexts: Retrieved context documents
            ground_truth: Ground truth answer (if available, for recall)

        Returns:
            RAGASResult with metric scores
        """
        try:
            if self.ragas_available and self.use_full_ragas:
                # Use actual RAGAS library
                metrics = await self._evaluate_with_ragas(
                    question, answer, contexts, ground_truth
                )
            else:
                # Use heuristic approximations
                metrics = await self._evaluate_heuristic(
                    question, answer, contexts, ground_truth
                )

            return RAGASResult(
                metrics=metrics,
                success=True,
                details={
                    "question_length": len(question),
                    "answer_length": len(answer),
                    "num_contexts": len(contexts)
                }
            )

        except Exception as e:
            logger.error(f"RAGAS evaluation failed: {e}")
            return RAGASResult(
                metrics=RAGASMetrics(),
                success=False,
                error=str(e)
            )

    async def _evaluate_with_ragas(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str]
    ) -> RAGASMetrics:
        """Evaluate using actual RAGAS library"""
        # This would use the real RAGAS library
        # For now, fallback to heuristics
        return await self._evaluate_heuristic(
            question, answer, contexts, ground_truth
        )

    async def _evaluate_heuristic(
        self,
        question: str,
        answer: str,
        contexts: List[str],
        ground_truth: Optional[str]
    ) -> RAGASMetrics:
        """
        Evaluate using heuristic approximations.

        These are simplified versions of RAGAS metrics for Phase 4.
        Phase 5 will integrate full RAGAS with embedding models.
        """
        # Faithfulness: How well is answer grounded in context?
        faithfulness = self._compute_faithfulness(answer, contexts)

        # Answer Relevancy: How relevant is answer to question?
        relevancy = self._compute_relevancy(question, answer)

        # Context Precision: How precise is the context?
        precision = self._compute_context_precision(question, contexts)

        # Context Recall: How much of ground truth is in context?
        recall = self._compute_context_recall(contexts, ground_truth) if ground_truth else 0.8

        return RAGASMetrics(
            faithfulness=faithfulness,
            answer_relevancy=relevancy,
            context_precision=precision,
            context_recall=recall
        )

    def _compute_faithfulness(self, answer: str, contexts: List[str]) -> float:
        """
        Compute faithfulness score.

        Measures how well answer is grounded in provided context.
        Heuristic: ratio of answer content found in contexts.
        """
        if not contexts or not answer:
            return 0.0

        # Combine all contexts
        combined_context = " ".join(contexts).lower()
        answer_lower = answer.lower()

        # Extract sentences/claims from answer
        answer_sentences = [s.strip() for s in answer.split(".") if s.strip()]

        if not answer_sentences:
            return 0.0

        # Check how many answer sentences have support in context
        supported = 0
        for sentence in answer_sentences:
            # Simple heuristic: check if significant words appear in context
            words = [w for w in sentence.split() if len(w) > 3]
            if words:
                matches = sum(1 for w in words if w in combined_context)
                if matches / len(words) > 0.5:  # 50% of words found
                    supported += 1

        faithfulness = supported / len(answer_sentences)

        logger.debug(
            f"Faithfulness: {supported}/{len(answer_sentences)} "
            f"sentences supported = {faithfulness:.2f}"
        )

        return faithfulness

    def _compute_relevancy(self, question: str, answer: str) -> float:
        """
        Compute answer relevancy score.

        Measures how relevant answer is to the question.
        Heuristic: keyword overlap and answer completeness.
        """
        if not question or not answer:
            return 0.0

        question_lower = question.lower()
        answer_lower = answer.lower()

        # Extract question keywords (remove stopwords)
        stopwords = {"what", "how", "why", "when", "where", "who", "is", "are", "the", "a", "an"}
        question_words = [
            w for w in question_lower.split()
            if len(w) > 3 and w not in stopwords
        ]

        if not question_words:
            return 0.5  # Default if can't determine

        # Check keyword coverage in answer
        keyword_coverage = sum(1 for w in question_words if w in answer_lower) / len(question_words)

        # Check answer length (too short may be incomplete)
        length_score = min(1.0, len(answer) / 200)  # Expect at least 200 chars

        # Combine scores
        relevancy = (keyword_coverage * 0.7 + length_score * 0.3)

        logger.debug(
            f"Relevancy: keyword_coverage={keyword_coverage:.2f}, "
            f"length_score={length_score:.2f}, "
            f"total={relevancy:.2f}"
        )

        return relevancy

    def _compute_context_precision(self, question: str, contexts: List[str]) -> float:
        """
        Compute context precision score.

        Measures how precise/relevant the retrieved contexts are.
        Heuristic: average relevance of contexts to question.
        """
        if not contexts or not question:
            return 0.0

        question_lower = question.lower()
        stopwords = {"what", "how", "why", "when", "where", "who", "is", "are", "the", "a", "an"}
        question_words = [
            w for w in question_lower.split()
            if len(w) > 3 and w not in stopwords
        ]

        if not question_words:
            return 0.5

        # Score each context
        context_scores = []
        for context in contexts:
            context_lower = context.lower()
            matches = sum(1 for w in question_words if w in context_lower)
            score = matches / len(question_words)
            context_scores.append(score)

        precision = sum(context_scores) / len(context_scores)

        logger.debug(
            f"Context Precision: avg of {len(context_scores)} contexts = {precision:.2f}"
        )

        return precision

    def _compute_context_recall(
        self,
        contexts: List[str],
        ground_truth: Optional[str]
    ) -> float:
        """
        Compute context recall score.

        Measures how much of the ground truth is captured in contexts.
        Heuristic: ratio of ground truth content found in contexts.
        """
        if not ground_truth or not contexts:
            return 0.8  # Default when no ground truth

        ground_truth_lower = ground_truth.lower()
        combined_context = " ".join(contexts).lower()

        # Extract ground truth sentences
        truth_sentences = [s.strip() for s in ground_truth.split(".") if s.strip()]

        if not truth_sentences:
            return 0.8

        # Check coverage
        covered = 0
        for sentence in truth_sentences:
            words = [w for w in sentence.split() if len(w) > 3]
            if words:
                matches = sum(1 for w in words if w in combined_context)
                if matches / len(words) > 0.5:
                    covered += 1

        recall = covered / len(truth_sentences)

        logger.debug(
            f"Context Recall: {covered}/{len(truth_sentences)} "
            f"truth sentences covered = {recall:.2f}"
        )

        return recall

    async def evaluate_batch(
        self,
        evaluations: List[Dict[str, Any]]
    ) -> List[RAGASResult]:
        """
        Evaluate multiple Q&A pairs in batch.

        Args:
            evaluations: List of dicts with keys:
                - question: str
                - answer: str
                - contexts: List[str]
                - ground_truth: Optional[str]

        Returns:
            List of RAGASResult
        """
        tasks = [
            self.evaluate(
                question=eval_data["question"],
                answer=eval_data["answer"],
                contexts=eval_data.get("contexts", []),
                ground_truth=eval_data.get("ground_truth")
            )
            for eval_data in evaluations
        ]

        results = await asyncio.gather(*tasks)
        return results

    def passes_quality_threshold(self, metrics: RAGASMetrics) -> bool:
        """
        Check if metrics pass quality thresholds.

        Args:
            metrics: RAGAS metrics to check

        Returns:
            True if meets minimum quality standards
        """
        return (
            metrics.faithfulness >= self.min_faithfulness and
            metrics.answer_relevancy >= self.min_relevancy
        )

    async def get_quality_summary(
        self,
        results: List[RAGASResult]
    ) -> Dict[str, Any]:
        """
        Get summary statistics across multiple evaluations.

        Args:
            results: List of RAGAS evaluation results

        Returns:
            Summary statistics
        """
        if not results:
            return {
                "total_evaluations": 0,
                "average_metrics": RAGASMetrics().to_dict(),
                "pass_rate": 0.0
            }

        successful = [r for r in results if r.success]

        if not successful:
            return {
                "total_evaluations": len(results),
                "successful_evaluations": 0,
                "average_metrics": RAGASMetrics().to_dict(),
                "pass_rate": 0.0
            }

        # Calculate averages
        avg_faithfulness = sum(r.metrics.faithfulness for r in successful) / len(successful)
        avg_relevancy = sum(r.metrics.answer_relevancy for r in successful) / len(successful)
        avg_precision = sum(r.metrics.context_precision for r in successful) / len(successful)
        avg_recall = sum(r.metrics.context_recall for r in successful) / len(successful)

        avg_metrics = RAGASMetrics(
            faithfulness=avg_faithfulness,
            answer_relevancy=avg_relevancy,
            context_precision=avg_precision,
            context_recall=avg_recall
        )

        # Calculate pass rate
        passing = sum(
            1 for r in successful
            if self.passes_quality_threshold(r.metrics)
        )
        pass_rate = passing / len(successful)

        return {
            "total_evaluations": len(results),
            "successful_evaluations": len(successful),
            "average_metrics": avg_metrics.to_dict(),
            "pass_rate": pass_rate,
            "passing_count": passing,
            "min_scores": {
                "faithfulness": min(r.metrics.faithfulness for r in successful),
                "answer_relevancy": min(r.metrics.answer_relevancy for r in successful),
                "context_precision": min(r.metrics.context_precision for r in successful),
                "context_recall": min(r.metrics.context_recall for r in successful),
            },
            "max_scores": {
                "faithfulness": max(r.metrics.faithfulness for r in successful),
                "answer_relevancy": max(r.metrics.answer_relevancy for r in successful),
                "context_precision": max(r.metrics.context_precision for r in successful),
                "context_recall": max(r.metrics.context_recall for r in successful),
            }
        }
