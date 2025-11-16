"""
Multi-Layer Validation Pipeline

Provides comprehensive validation for research tools and outputs:
- Schema validation (Pydantic models)
- Format validation (data types, structures)
- Quality validation (completeness, coherence)
- Hallucination detection (claim verification)
- Chain validation (tool output compatibility)
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Callable
from enum import Enum
import re

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """Severity levels for validation issues"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class ValidationIssue:
    """A single validation issue"""
    validator: str
    severity: ValidationSeverity
    message: str
    field_name: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Result of validation process"""
    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def has_errors(self) -> bool:
        """Check if result has error-level issues"""
        return any(
            issue.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]
            for issue in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        """Check if result has warnings"""
        return any(issue.severity == ValidationSeverity.WARNING for issue in self.issues)

    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """Get all issues of a specific severity"""
        return [issue for issue in self.issues if issue.severity == severity]


class BaseValidator(ABC):
    """Base class for all validators"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def validate(self, data: Any, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Validate data.

        Args:
            data: Data to validate
            context: Additional context for validation

        Returns:
            ValidationResult with issues and metadata
        """
        pass


class SchemaValidator(BaseValidator):
    """
    Validates data against Pydantic schemas.

    Ensures tool inputs and outputs conform to expected structure.
    """

    def __init__(self, schema: type[BaseModel]):
        super().__init__(name=f"schema_{schema.__name__}")
        self.schema = schema

    async def validate(self, data: Any, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Validate data against Pydantic schema"""
        try:
            # Attempt to parse/validate
            if isinstance(data, dict):
                self.schema(**data)
            else:
                # Assume data is already an instance
                if not isinstance(data, self.schema):
                    return ValidationResult(
                        valid=False,
                        issues=[
                            ValidationIssue(
                                validator=self.name,
                                severity=ValidationSeverity.ERROR,
                                message=f"Data is not an instance of {self.schema.__name__}",
                            )
                        ]
                    )

            return ValidationResult(
                valid=True,
                metadata={"schema": self.schema.__name__}
            )

        except ValidationError as e:
            issues = []
            for error in e.errors():
                issues.append(
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.ERROR,
                        message=error["msg"],
                        field_name=".".join(str(loc) for loc in error["loc"]),
                        details={"type": error["type"]}
                    )
                )

            return ValidationResult(
                valid=False,
                issues=issues,
                metadata={"schema": self.schema.__name__}
            )

        except Exception as e:
            return ValidationResult(
                valid=False,
                issues=[
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Unexpected validation error: {str(e)}"
                    )
                ]
            )


class FormatValidator(BaseValidator):
    """
    Validates data formats and structures.

    Checks:
    - Required fields present
    - Data types correct
    - Value ranges valid
    - Format patterns (URLs, emails, etc.)
    """

    def __init__(self, rules: Dict[str, Dict[str, Any]]):
        """
        Initialize format validator.

        Args:
            rules: Validation rules per field
                {
                    "field_name": {
                        "type": str,
                        "required": True,
                        "pattern": r"^https?://",
                        "min_length": 10,
                        "max_length": 1000
                    }
                }
        """
        super().__init__(name="format_validator")
        self.rules = rules

    async def validate(self, data: Any, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Validate data format"""
        if not isinstance(data, dict):
            return ValidationResult(
                valid=False,
                issues=[
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.ERROR,
                        message="Data must be a dictionary"
                    )
                ]
            )

        issues = []

        for field_name, field_rules in self.rules.items():
            # Check required fields
            if field_rules.get("required", False) and field_name not in data:
                issues.append(
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.ERROR,
                        message=f"Required field '{field_name}' missing",
                        field_name=field_name
                    )
                )
                continue

            # Skip if field not present and not required
            if field_name not in data:
                continue

            value = data[field_name]

            # Check type
            expected_type = field_rules.get("type")
            if expected_type and not isinstance(value, expected_type):
                issues.append(
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.ERROR,
                        message=f"Field '{field_name}' has wrong type. Expected {expected_type.__name__}, got {type(value).__name__}",
                        field_name=field_name
                    )
                )
                continue

            # Check pattern (for strings)
            pattern = field_rules.get("pattern")
            if pattern and isinstance(value, str):
                if not re.match(pattern, value):
                    issues.append(
                        ValidationIssue(
                            validator=self.name,
                            severity=ValidationSeverity.WARNING,
                            message=f"Field '{field_name}' does not match expected pattern",
                            field_name=field_name,
                            details={"pattern": pattern}
                        )
                    )

            # Check length constraints
            if hasattr(value, "__len__"):
                min_len = field_rules.get("min_length")
                max_len = field_rules.get("max_length")

                if min_len is not None and len(value) < min_len:
                    issues.append(
                        ValidationIssue(
                            validator=self.name,
                            severity=ValidationSeverity.WARNING,
                            message=f"Field '{field_name}' is too short (min: {min_len}, got: {len(value)})",
                            field_name=field_name
                        )
                    )

                if max_len is not None and len(value) > max_len:
                    issues.append(
                        ValidationIssue(
                            validator=self.name,
                            severity=ValidationSeverity.WARNING,
                            message=f"Field '{field_name}' is too long (max: {max_len}, got: {len(value)})",
                            field_name=field_name
                        )
                    )

            # Check value range (for numbers)
            if isinstance(value, (int, float)):
                min_val = field_rules.get("min_value")
                max_val = field_rules.get("max_value")

                if min_val is not None and value < min_val:
                    issues.append(
                        ValidationIssue(
                            validator=self.name,
                            severity=ValidationSeverity.WARNING,
                            message=f"Field '{field_name}' is below minimum (min: {min_val}, got: {value})",
                            field_name=field_name
                        )
                    )

                if max_val is not None and value > max_val:
                    issues.append(
                        ValidationIssue(
                            validator=self.name,
                            severity=ValidationSeverity.WARNING,
                            message=f"Field '{field_name}' exceeds maximum (max: {max_val}, got: {value})",
                            field_name=field_name
                        )
                    )

        return ValidationResult(
            valid=len([i for i in issues if i.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]]) == 0,
            issues=issues,
            metadata={"fields_validated": len(self.rules)}
        )


class QualityValidator(BaseValidator):
    """
    Validates quality of research outputs.

    Checks:
    - Completeness (all required information present)
    - Coherence (output makes logical sense)
    - Relevance (output relates to query)
    - Specificity (output has concrete details)
    """

    def __init__(self, min_completeness: float = 0.7):
        super().__init__(name="quality_validator")
        self.min_completeness = min_completeness

    async def validate(self, data: Any, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Validate output quality"""
        issues = []
        metadata = {}

        # Extract text content for analysis
        text_content = self._extract_text(data)

        if not text_content:
            return ValidationResult(
                valid=False,
                issues=[
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.ERROR,
                        message="No text content found to validate"
                    )
                ]
            )

        # Check completeness
        completeness_score = self._check_completeness(text_content, context)
        metadata["completeness_score"] = completeness_score

        if completeness_score < self.min_completeness:
            issues.append(
                ValidationIssue(
                    validator=self.name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Output completeness below threshold ({completeness_score:.2f} < {self.min_completeness})",
                    details={"completeness_score": completeness_score}
                )
            )

        # Check for empty or very short content
        if len(text_content.strip()) < 50:
            issues.append(
                ValidationIssue(
                    validator=self.name,
                    severity=ValidationSeverity.WARNING,
                    message="Output is very short, may lack detail",
                    details={"length": len(text_content)}
                )
            )

        # Check for coherence (basic heuristics)
        coherence_score = self._check_coherence(text_content)
        metadata["coherence_score"] = coherence_score

        if coherence_score < 0.5:
            issues.append(
                ValidationIssue(
                    validator=self.name,
                    severity=ValidationSeverity.WARNING,
                    message="Output may lack coherence",
                    details={"coherence_score": coherence_score}
                )
            )

        # Check relevance to query (if query provided)
        if context and "query" in context:
            relevance_score = self._check_relevance(text_content, context["query"])
            metadata["relevance_score"] = relevance_score

            if relevance_score < 0.3:
                issues.append(
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.WARNING,
                        message="Output may not be relevant to query",
                        details={"relevance_score": relevance_score}
                    )
                )

        return ValidationResult(
            valid=not any(i.severity == ValidationSeverity.ERROR for i in issues),
            issues=issues,
            metadata=metadata
        )

    def _extract_text(self, data: Any) -> str:
        """Extract text content from various data structures"""
        if isinstance(data, str):
            return data
        elif isinstance(data, dict):
            # Try common text fields
            for field in ["text", "content", "answer", "result", "summary", "description"]:
                if field in data and isinstance(data[field], str):
                    return data[field]
            # Concatenate all string values
            return " ".join(str(v) for v in data.values() if isinstance(v, str))
        elif isinstance(data, list):
            return " ".join(self._extract_text(item) for item in data)
        return str(data)

    def _check_completeness(self, text: str, context: Optional[Dict] = None) -> float:
        """
        Check completeness of output.

        Heuristics:
        - Presence of key information indicators
        - Length relative to expected
        - Sentence structure
        """
        score = 0.0

        # Length score (normalized)
        if len(text) > 500:
            score += 0.4
        elif len(text) > 200:
            score += 0.2

        # Sentence count
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if len(sentences) >= 3:
            score += 0.3
        elif len(sentences) >= 1:
            score += 0.15

        # Presence of concrete details (numbers, dates, names)
        if re.search(r"\d+", text):
            score += 0.15

        if re.search(r"\b[A-Z][a-z]+\s[A-Z][a-z]+\b", text):  # Proper names
            score += 0.15

        return min(score, 1.0)

    def _check_coherence(self, text: str) -> float:
        """
        Check coherence of output.

        Simple heuristics:
        - Reasonable sentence structure
        - Not excessive repetition
        - Logical flow indicators
        """
        score = 0.5  # Base score

        # Check for logical connectors
        connectors = ["therefore", "however", "because", "additionally", "furthermore", "moreover"]
        if any(connector in text.lower() for connector in connectors):
            score += 0.2

        # Check for complete sentences
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if sentences:
            avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences)
            if 5 <= avg_sentence_length <= 30:  # Reasonable sentence length
                score += 0.2

        # Check for excessive repetition
        words = text.lower().split()
        if len(words) > 10:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:  # Too repetitive
                score -= 0.3

        return max(0.0, min(score, 1.0))

    def _check_relevance(self, text: str, query: str) -> float:
        """
        Check relevance to query.

        Simple keyword overlap heuristic.
        """
        # Extract keywords from query (simple: remove stopwords)
        stopwords = {"the", "a", "an", "in", "on", "at", "to", "for", "of", "is", "are", "was", "were"}
        query_words = set(
            word.lower() for word in query.split()
            if word.lower() not in stopwords and len(word) > 2
        )

        if not query_words:
            return 0.5  # Can't determine

        text_lower = text.lower()
        matches = sum(1 for word in query_words if word in text_lower)

        return matches / len(query_words)


class HallucinationDetector(BaseValidator):
    """
    Detects potential hallucinations in research outputs.

    Checks:
    - Claims are supported by sources
    - No contradictory information
    - Confidence indicators present
    - Speculation is marked as such
    """

    def __init__(self):
        super().__init__(name="hallucination_detector")

    async def validate(self, data: Any, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Detect potential hallucinations"""
        issues = []
        metadata = {}

        # Extract text content
        if isinstance(data, dict) and "content" in data:
            text_content = data["content"]
            sources = data.get("sources", [])
        elif isinstance(data, str):
            text_content = data
            sources = context.get("sources", []) if context else []
        else:
            text_content = str(data)
            sources = []

        # Check for unsupported claims
        if sources:
            # Count citations/references
            citation_count = len(re.findall(r"\[(\d+|[a-z]+)\]", text_content))
            metadata["citation_count"] = citation_count
            metadata["source_count"] = len(sources)

            # Heuristic: should have at least 1 citation per 2 sources
            expected_citations = len(sources) // 2
            if citation_count < expected_citations:
                issues.append(
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.WARNING,
                        message=f"Few citations found ({citation_count}) relative to sources ({len(sources)})",
                        details={"citation_count": citation_count, "source_count": len(sources)}
                    )
                )

        # Check for speculation without markers
        speculation_words = ["might", "could", "possibly", "perhaps", "likely", "may"]
        certainty_words = ["definitely", "certainly", "always", "never", "absolutely"]

        has_speculation = any(word in text_content.lower() for word in speculation_words)
        has_certainty = any(word in text_content.lower() for word in certainty_words)

        metadata["has_speculation_markers"] = has_speculation
        metadata["has_certainty_markers"] = has_certainty

        # Flag if making certain claims without sources
        if has_certainty and not sources:
            issues.append(
                ValidationIssue(
                    validator=self.name,
                    severity=ValidationSeverity.WARNING,
                    message="Output makes certain claims without providing sources",
                    details={"certainty_markers": has_certainty}
                )
            )

        # Check for contradictory statements (basic)
        contradictions = self._detect_contradictions(text_content)
        if contradictions:
            metadata["potential_contradictions"] = len(contradictions)
            issues.append(
                ValidationIssue(
                    validator=self.name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Detected {len(contradictions)} potential contradictions",
                    details={"contradictions": contradictions}
                )
            )

        return ValidationResult(
            valid=not any(i.severity == ValidationSeverity.ERROR for i in issues),
            issues=issues,
            metadata=metadata
        )

    def _detect_contradictions(self, text: str) -> List[str]:
        """
        Detect potential contradictions.

        Simple heuristic: look for negation patterns.
        """
        contradictions = []

        # Look for "X is Y" followed later by "X is not Y"
        # This is a very basic implementation
        sentences = [s.strip() for s in text.split(".") if s.strip()]

        for i, sent1 in enumerate(sentences):
            for sent2 in sentences[i+1:]:
                # Very basic: check for "not" appearing in similar sentences
                words1 = set(sent1.lower().split())
                words2 = set(sent2.lower().split())

                overlap = words1 & words2
                if len(overlap) > 3:  # Significant overlap
                    if ("not" in words1) != ("not" in words2):  # One has "not", other doesn't
                        contradictions.append(f"{sent1[:50]}... vs {sent2[:50]}...")

        return contradictions[:3]  # Return max 3 examples


class ChainValidator(BaseValidator):
    """
    Validates compatibility between chained tools.

    Ensures output from one tool is valid input for the next tool.
    """

    def __init__(self, output_schema: Optional[type[BaseModel]] = None,
                 next_input_schema: Optional[type[BaseModel]] = None):
        super().__init__(name="chain_validator")
        self.output_schema = output_schema
        self.next_input_schema = next_input_schema

    async def validate(self, data: Any, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """Validate tool chain compatibility"""
        issues = []

        # If we have schemas, validate compatibility
        if self.output_schema and self.next_input_schema:
            # Check if output fields match expected input fields
            output_fields = set(self.output_schema.model_fields.keys())
            input_fields = set(self.next_input_schema.model_fields.keys())

            missing_fields = input_fields - output_fields
            if missing_fields:
                issues.append(
                    ValidationIssue(
                        validator=self.name,
                        severity=ValidationSeverity.ERROR,
                        message=f"Output missing required fields for next tool: {missing_fields}",
                        details={"missing_fields": list(missing_fields)}
                    )
                )

        # Validate data structure is passable
        if not isinstance(data, (dict, list, str, int, float, bool, type(None))):
            issues.append(
                ValidationIssue(
                    validator=self.name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Output type {type(data)} may not be serializable for chaining"
                )
            )

        return ValidationResult(
            valid=len([i for i in issues if i.severity == ValidationSeverity.ERROR]) == 0,
            issues=issues
        )


class ValidationPipeline:
    """
    Orchestrates multiple validators in sequence.

    Runs validators in order, collecting all issues.
    Can fail fast or continue on errors.
    """

    def __init__(self, validators: List[BaseValidator], fail_fast: bool = False):
        """
        Initialize validation pipeline.

        Args:
            validators: List of validators to run in order
            fail_fast: If True, stop on first error
        """
        self.validators = validators
        self.fail_fast = fail_fast

    async def validate(self, data: Any, context: Optional[Dict[str, Any]] = None) -> ValidationResult:
        """
        Run all validators on data.

        Args:
            data: Data to validate
            context: Additional context for validators

        Returns:
            Combined ValidationResult from all validators
        """
        all_issues = []
        all_metadata = {}

        for validator in self.validators:
            logger.debug(f"Running validator: {validator.name}")

            try:
                result = await validator.validate(data, context)

                # Collect issues
                all_issues.extend(result.issues)

                # Merge metadata
                all_metadata[validator.name] = result.metadata

                # Check fail_fast
                if self.fail_fast and result.has_errors:
                    logger.warning(f"Validator {validator.name} failed, stopping pipeline (fail_fast=True)")
                    return ValidationResult(
                        valid=False,
                        issues=all_issues,
                        metadata=all_metadata
                    )

            except Exception as e:
                logger.error(f"Validator {validator.name} raised exception: {e}")
                all_issues.append(
                    ValidationIssue(
                        validator=validator.name,
                        severity=ValidationSeverity.CRITICAL,
                        message=f"Validator failed with exception: {str(e)}"
                    )
                )

                if self.fail_fast:
                    return ValidationResult(
                        valid=False,
                        issues=all_issues,
                        metadata=all_metadata
                    )

        # Determine overall validity
        has_errors = any(
            issue.severity in [ValidationSeverity.ERROR, ValidationSeverity.CRITICAL]
            for issue in all_issues
        )

        return ValidationResult(
            valid=not has_errors,
            issues=all_issues,
            metadata=all_metadata
        )

    def add_validator(self, validator: BaseValidator):
        """Add a validator to the pipeline"""
        self.validators.append(validator)

    def remove_validator(self, validator_name: str):
        """Remove a validator by name"""
        self.validators = [v for v in self.validators if v.name != validator_name]


# Convenience function for creating common validation pipelines
def create_research_output_pipeline(
    output_schema: Optional[type[BaseModel]] = None,
    min_completeness: float = 0.7,
    fail_fast: bool = False
) -> ValidationPipeline:
    """
    Create a standard validation pipeline for research outputs.

    Args:
        output_schema: Pydantic schema for output validation
        min_completeness: Minimum completeness score
        fail_fast: Stop on first error

    Returns:
        Configured ValidationPipeline
    """
    validators = []

    # Schema validation (if provided)
    if output_schema:
        validators.append(SchemaValidator(output_schema))

    # Quality validation
    validators.append(QualityValidator(min_completeness=min_completeness))

    # Hallucination detection
    validators.append(HallucinationDetector())

    return ValidationPipeline(validators, fail_fast=fail_fast)
