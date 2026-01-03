"""
Enhanced Extraction Schemas for Dataset Generation

Provides structured types for academic claim extraction, dataset entry
formatting, and quality evaluation for fine-tuning pipelines.

Extends the base research types with academic-specific claim types
and Alpaca format dataset entries.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict, Any
import json
import uuid

from .types import fingerprint


class ClaimType(str, Enum):
    """
    Academic claim type classification.

    More granular than fact/opinion/recommendation for academic papers.
    """
    FINDING = "finding"           # Empirical result or observation
    METHOD = "method"             # Technique, algorithm, or approach
    DEFINITION = "definition"     # Concept definition or clarification
    COMPARISON = "comparison"     # Comparative statement between approaches
    LIMITATION = "limitation"     # Known constraint or weakness
    HYPOTHESIS = "hypothesis"     # Proposed explanation or prediction
    CONTRIBUTION = "contribution" # Stated paper contribution


class SectionType(str, Enum):
    """
    Academic paper section classification.

    Used to track provenance and weight claims appropriately.
    Results and conclusions typically carry more weight than introductions.
    """
    ABSTRACT = "abstract"
    INTRODUCTION = "introduction"
    BACKGROUND = "background"
    METHODS = "methods"
    RESULTS = "results"
    DISCUSSION = "discussion"
    CONCLUSION = "conclusion"
    RELATED_WORK = "related_work"
    UNKNOWN = "unknown"


class EvaluationDecision(str, Enum):
    """
    Collective evaluation decision for claims/entries.
    """
    ACCEPT = "accept"       # High quality, include in dataset
    REFINE = "refine"       # Needs improvement before inclusion
    REJECT = "reject"       # Low quality, exclude from dataset
    PENDING = "pending"     # Not yet evaluated


@dataclass
class EvidenceQuote:
    """
    A verbatim quote from a paper supporting a claim.

    Enhanced version of EvidenceSpan with paper reference.
    """
    paper_id: str               # research_papers.id
    quote: str                  # Exact verbatim text
    section: SectionType        # Which section this quote came from
    page_number: Optional[int] = None
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    context: str = ""           # Surrounding text for context

    def to_dict(self) -> Dict[str, Any]:
        return {
            "paper_id": self.paper_id,
            "quote": self.quote,
            "section": self.section.value,
            "page_number": self.page_number,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "context": self.context,
        }


@dataclass
class ExtractedClaim:
    """
    An atomic claim extracted from a research paper.

    This is the intermediate representation between raw paper content
    and the final dataset entry. Claims are verified and evaluated
    before being converted to instruction-output pairs.

    Attributes:
        id: Unique claim identifier (UUID)
        paper_id: Foreign key to research_papers table
        claim_text: The claim statement
        claim_type: Academic claim type classification
        section: Which paper section the claim came from
        evidence_quotes: List of supporting quotes
        confidence: Extraction confidence 0-1
        provenance_score: Quote coverage score 0-1
        embedding_id: Qdrant embedding ID for similarity search
        evaluation_status: Collective evaluation decision
        evaluation_scores: Per-agent evaluation scores
        refinement_notes: Notes from refinement attempts
        created_at: Extraction timestamp
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    paper_id: str = ""
    claim_text: str = ""
    claim_type: ClaimType = ClaimType.FINDING
    section: SectionType = SectionType.UNKNOWN
    evidence_quotes: List[EvidenceQuote] = field(default_factory=list)
    confidence: float = 0.0
    provenance_score: float = 0.0
    embedding_id: Optional[str] = None
    evaluation_status: EvaluationDecision = EvaluationDecision.PENDING
    evaluation_scores: Dict[str, float] = field(default_factory=dict)
    refinement_notes: str = ""
    dedupe_fingerprint: str = ""
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if not self.dedupe_fingerprint:
            self.dedupe_fingerprint = fingerprint(self.claim_text)
        if not self.created_at:
            self.created_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "claim_text": self.claim_text,
            "claim_type": self.claim_type.value,
            "section": self.section.value,
            "evidence_quotes": [q.to_dict() for q in self.evidence_quotes],
            "confidence": self.confidence,
            "provenance_score": self.provenance_score,
            "embedding_id": self.embedding_id,
            "evaluation_status": self.evaluation_status.value,
            "evaluation_scores": self.evaluation_scores,
            "refinement_notes": self.refinement_notes,
            "dedupe_fingerprint": self.dedupe_fingerprint,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExtractedClaim":
        """Create from dictionary representation."""
        evidence_quotes = [
            EvidenceQuote(
                paper_id=q["paper_id"],
                quote=q["quote"],
                section=SectionType(q["section"]),
                page_number=q.get("page_number"),
                char_start=q.get("char_start"),
                char_end=q.get("char_end"),
                context=q.get("context", ""),
            )
            for q in data.get("evidence_quotes", [])
        ]

        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            id=data.get("id", uuid.uuid4().hex),
            paper_id=data.get("paper_id", ""),
            claim_text=data.get("claim_text", ""),
            claim_type=ClaimType(data.get("claim_type", "finding")),
            section=SectionType(data.get("section", "unknown")),
            evidence_quotes=evidence_quotes,
            confidence=data.get("confidence", 0.0),
            provenance_score=data.get("provenance_score", 0.0),
            embedding_id=data.get("embedding_id"),
            evaluation_status=EvaluationDecision(data.get("evaluation_status", "pending")),
            evaluation_scores=data.get("evaluation_scores", {}),
            refinement_notes=data.get("refinement_notes", ""),
            dedupe_fingerprint=data.get("dedupe_fingerprint", ""),
            created_at=created_at,
        )


@dataclass
class DatasetEntry:
    """
    An instruction-output pair for fine-tuning in Alpaca format.

    This is the final format used for training. Each entry is derived
    from one or more ExtractedClaims after collective evaluation.

    Alpaca format:
    {
        "instruction": "Explain quantum entanglement...",
        "input": "",  # Optional additional context
        "output": "Quantum entanglement is..."
    }

    Attributes:
        id: Unique entry identifier
        topic_id: Foreign key to research_topics table
        instruction: The prompt/question
        input: Optional additional context
        output: The desired response
        source_claim_ids: Claims this entry was derived from
        source_paper_ids: Papers contributing to this entry
        quality_score: Overall quality score 0-1
        evaluation_status: Collective evaluation decision
        training_batch_id: Assigned batch for training (optional)
        metadata: Additional metadata (authors, sources, etc.)
        created_at: Creation timestamp
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    topic_id: str = ""
    instruction: str = ""
    input: str = ""
    output: str = ""
    source_claim_ids: List[str] = field(default_factory=list)
    source_paper_ids: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    evaluation_status: EvaluationDecision = EvaluationDecision.PENDING
    training_batch_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow()

    def to_alpaca_dict(self) -> Dict[str, str]:
        """Convert to Alpaca format for training."""
        return {
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
        }

    def to_dict(self) -> Dict[str, Any]:
        """Convert to full dictionary representation."""
        return {
            "id": self.id,
            "topic_id": self.topic_id,
            "instruction": self.instruction,
            "input": self.input,
            "output": self.output,
            "source_claim_ids": self.source_claim_ids,
            "source_paper_ids": self.source_paper_ids,
            "quality_score": self.quality_score,
            "evaluation_status": self.evaluation_status.value,
            "training_batch_id": self.training_batch_id,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DatasetEntry":
        """Create from dictionary representation."""
        created_at = None
        if data.get("created_at"):
            created_at = datetime.fromisoformat(data["created_at"])

        return cls(
            id=data.get("id", uuid.uuid4().hex),
            topic_id=data.get("topic_id", ""),
            instruction=data.get("instruction", ""),
            input=data.get("input", ""),
            output=data.get("output", ""),
            source_claim_ids=data.get("source_claim_ids", []),
            source_paper_ids=data.get("source_paper_ids", []),
            quality_score=data.get("quality_score", 0.0),
            evaluation_status=EvaluationDecision(data.get("evaluation_status", "pending")),
            training_batch_id=data.get("training_batch_id"),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )

    @classmethod
    def from_claim(
        cls,
        claim: ExtractedClaim,
        topic_id: str,
        instruction_template: str = "Explain the following research finding:",
    ) -> "DatasetEntry":
        """
        Create a dataset entry from an extracted claim.

        Args:
            claim: The extracted claim
            topic_id: Research topic ID
            instruction_template: Template for generating instruction

        Returns:
            DatasetEntry in Alpaca format
        """
        # Build instruction from template and claim context
        instruction = instruction_template

        # Build output from claim with evidence
        output_parts = [claim.claim_text]

        if claim.evidence_quotes:
            output_parts.append("\n\nSupporting evidence:")
            for i, quote in enumerate(claim.evidence_quotes[:3], 1):  # Limit to 3 quotes
                output_parts.append(f'{i}. "{quote.quote}"')

        output = "\n".join(output_parts)

        return cls(
            topic_id=topic_id,
            instruction=instruction,
            input=claim.claim_text,
            output=output,
            source_claim_ids=[claim.id],
            source_paper_ids=[claim.paper_id] if claim.paper_id else [],
            quality_score=claim.confidence,
            evaluation_status=EvaluationDecision.PENDING,
            metadata={
                "claim_type": claim.claim_type.value,
                "section": claim.section.value,
                "provenance_score": claim.provenance_score,
            },
        )


@dataclass
class TrainingBatch:
    """
    A batch of dataset entries ready for training.

    Batches are created when enough high-quality entries accumulate.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    topic_id: str = ""
    entry_count: int = 0
    file_path: str = ""          # Path to Alpaca JSON file
    status: str = "pending"      # pending, training, completed, failed
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    training_config: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow()


def export_entries_to_alpaca(
    entries: List[DatasetEntry],
    output_path: str,
    include_metadata: bool = False,
) -> int:
    """
    Export dataset entries to Alpaca JSON format.

    Args:
        entries: List of dataset entries to export
        output_path: Path to write JSON file
        include_metadata: Whether to include extra fields beyond Alpaca format

    Returns:
        Number of entries exported
    """
    if include_metadata:
        data = [entry.to_dict() for entry in entries]
    else:
        data = [entry.to_alpaca_dict() for entry in entries]

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return len(data)


def compute_entry_quality_score(
    claim_confidence: float,
    provenance_score: float,
    output_length: int,
    has_evidence: bool,
    evaluation_scores: Optional[Dict[str, float]] = None,
) -> float:
    """
    Compute quality score for a dataset entry.

    Factors:
    - 25% claim extraction confidence
    - 25% provenance (quote coverage)
    - 15% output length (penalize too short or too long)
    - 15% has supporting evidence
    - 20% collective evaluation scores (if available)

    Args:
        claim_confidence: Original claim confidence
        provenance_score: Quote coverage score
        output_length: Character length of output
        has_evidence: Whether evidence quotes are included
        evaluation_scores: Optional dict of agent scores

    Returns:
        Quality score 0-1
    """
    # Output length scoring (optimal: 200-800 chars)
    if output_length < 50:
        length_score = 0.2
    elif output_length < 200:
        length_score = output_length / 200 * 0.8
    elif output_length <= 800:
        length_score = 1.0
    elif output_length <= 1500:
        length_score = 1.0 - (output_length - 800) / 1400 * 0.3
    else:
        length_score = 0.7

    evidence_score = 1.0 if has_evidence else 0.5

    # Average evaluation scores if available
    eval_score = 0.5  # Default neutral
    if evaluation_scores:
        eval_score = sum(evaluation_scores.values()) / len(evaluation_scores)

    quality = (
        0.25 * claim_confidence +
        0.25 * provenance_score +
        0.15 * length_score +
        0.15 * evidence_score +
        0.20 * eval_score
    )

    return min(1.0, max(0.0, quality))


# Instruction templates for different claim types
INSTRUCTION_TEMPLATES = {
    ClaimType.FINDING: [
        "Explain this research finding:",
        "What does this scientific observation mean?",
        "Describe this empirical result:",
    ],
    ClaimType.METHOD: [
        "How does this technique work?",
        "Explain this methodology:",
        "Describe this approach:",
    ],
    ClaimType.DEFINITION: [
        "Define this concept:",
        "What is the meaning of:",
        "Explain the definition of:",
    ],
    ClaimType.COMPARISON: [
        "Compare these approaches:",
        "How do these differ?",
        "Contrast the following:",
    ],
    ClaimType.LIMITATION: [
        "What are the limitations of this approach?",
        "Explain the constraints of:",
        "What are the weaknesses of:",
    ],
    ClaimType.HYPOTHESIS: [
        "Explain this hypothesis:",
        "What does this theory propose?",
        "Describe this prediction:",
    ],
    ClaimType.CONTRIBUTION: [
        "What is the contribution of this work?",
        "Summarize the key contribution:",
        "What does this paper contribute?",
    ],
}


def get_instruction_for_claim(claim: ExtractedClaim) -> str:
    """
    Get an appropriate instruction template for a claim type.

    Args:
        claim: The extracted claim

    Returns:
        Instruction string
    """
    import random

    templates = INSTRUCTION_TEMPLATES.get(
        claim.claim_type,
        ["Explain the following:"]
    )

    return random.choice(templates)
