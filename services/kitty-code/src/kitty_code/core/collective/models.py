"""
Data models for the Tiered Collective Architecture.

Defines the structured data types exchanged between Planner, Executor, and Judge roles.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class JudgmentVerdict(Enum):
    """
    Judge's verdict on executor output.

    APPROVE: Output meets criteria, proceed to next step or complete
    REVISE: Output needs improvement, provide feedback for re-execution
    REJECT: Output is fundamentally wrong, escalate to re-planning
    """

    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


@dataclass
class TaskStep:
    """
    A single step in the task plan.

    Represents one unit of work for the Executor (junior developer) to implement.
    Includes detailed instructions from the Planner (senior developer).
    """

    # Step identifier
    step_id: str

    # Human-readable description of what to do
    description: str

    # Success criteria (how Judge will evaluate)
    success_criteria: List[str] = field(default_factory=list)

    # Files expected to be modified
    expected_files: List[str] = field(default_factory=list)

    # Tools expected to be used
    expected_tools: List[str] = field(default_factory=list)

    # Dependencies on other steps (by step_id)
    depends_on: List[str] = field(default_factory=list)

    # Estimated complexity (0.0-1.0)
    complexity: float = 0.5

    # Whether this step is optional
    optional: bool = False

    # === Senior/Junior Delegation Fields ===

    # Detailed instructions for the junior developer (code examples, patterns)
    junior_instructions: str = ""

    # What the result should look like
    expected_output: str = ""

    # Warnings about common mistakes
    pitfalls: List[str] = field(default_factory=list)


@dataclass
class TaskPlan:
    """
    Strategic plan produced by the Planner (senior developer) role.

    Decomposes a complex user request into ordered, reviewable steps
    with detailed instructions for the Executor (junior developer).
    """

    # Plan identifier
    plan_id: str

    # Original user request
    user_request: str

    # High-level summary of approach
    summary: str

    # Ordered list of steps
    steps: List[TaskStep] = field(default_factory=list)

    # Overall success criteria
    success_criteria: List[str] = field(default_factory=list)

    # Estimated total complexity
    total_complexity: float = 0.5

    # Files that will be affected
    affected_files: List[str] = field(default_factory=list)

    # Timestamp
    created_at: datetime = field(default_factory=datetime.now)

    # Model that generated this plan
    model: str = ""

    # === Senior/Junior Delegation Fields ===

    # Note to junior developer (encouragement + key warnings)
    delegation_note: str = ""

    def get_step(self, step_id: str) -> Optional[TaskStep]:
        """Get a step by ID."""
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None

    def get_ready_steps(self, completed_step_ids: List[str]) -> List[TaskStep]:
        """Get steps whose dependencies are satisfied."""
        ready = []
        for step in self.steps:
            if step.step_id in completed_step_ids:
                continue
            if all(dep in completed_step_ids for dep in step.depends_on):
                ready.append(step)
        return ready

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "TaskPlan":
        """Parse TaskPlan from JSON (LLM output)."""
        steps = [
            TaskStep(
                step_id=s.get("step_id", f"step_{i}"),
                description=s.get("description", ""),
                success_criteria=s.get("success_criteria", []),
                expected_files=s.get("expected_files", []),
                expected_tools=s.get("expected_tools", []),
                depends_on=s.get("depends_on", []),
                complexity=s.get("complexity", 0.5),
                optional=s.get("optional", False),
                # New Senior/Junior delegation fields
                junior_instructions=s.get("junior_instructions", ""),
                expected_output=s.get("expected_output", ""),
                pitfalls=s.get("pitfalls", []),
            )
            for i, s in enumerate(data.get("steps", []))
        ]

        return cls(
            plan_id=data.get("plan_id", "plan_0"),
            user_request=data.get("user_request", ""),
            summary=data.get("summary", ""),
            steps=steps,
            success_criteria=data.get("success_criteria", []),
            total_complexity=data.get("total_complexity", 0.5),
            affected_files=data.get("affected_files", []),
            model=data.get("model", ""),
            # New Senior/Junior delegation field
            delegation_note=data.get("delegation_note", ""),
        )

    def to_json(self) -> Dict[str, Any]:
        """Convert to JSON for serialization."""
        return {
            "plan_id": self.plan_id,
            "user_request": self.user_request,
            "summary": self.summary,
            "delegation_note": self.delegation_note,
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "success_criteria": s.success_criteria,
                    "expected_files": s.expected_files,
                    "expected_tools": s.expected_tools,
                    "depends_on": s.depends_on,
                    "complexity": s.complexity,
                    "optional": s.optional,
                    # New Senior/Junior delegation fields
                    "junior_instructions": s.junior_instructions,
                    "expected_output": s.expected_output,
                    "pitfalls": s.pitfalls,
                }
                for s in self.steps
            ],
            "success_criteria": self.success_criteria,
            "total_complexity": self.total_complexity,
            "affected_files": self.affected_files,
            "created_at": self.created_at.isoformat(),
            "model": self.model,
        }


@dataclass
class ToolCall:
    """Record of a tool call made by the Executor."""

    tool_name: str
    arguments: Dict[str, Any]
    result: Any
    success: bool
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    """
    Result of Executor implementing a step.

    Contains tool calls, output, and metadata for Judge review.
    """

    # Which step this executed
    step_id: str

    # Tool calls made during execution
    tool_calls: List[ToolCall] = field(default_factory=list)

    # LLM's text response
    response_text: str = ""

    # Files modified
    files_modified: List[str] = field(default_factory=list)

    # Files created
    files_created: List[str] = field(default_factory=list)

    # Whether execution completed without errors
    success: bool = True

    # Error message if failed
    error: Optional[str] = None

    # Execution timing
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration_ms: int = 0

    # Model used
    model: str = ""

    # Token usage
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def complete(self) -> None:
        """Mark execution as complete and calculate duration."""
        self.completed_at = datetime.now()
        self.duration_ms = int(
            (self.completed_at - self.started_at).total_seconds() * 1000
        )

    def to_judge_context(self) -> Dict[str, Any]:
        """Format for Judge review (full visibility)."""
        return {
            "step_id": self.step_id,
            "tool_calls": [
                {
                    "tool": tc.tool_name,
                    "args": tc.arguments,
                    "result": str(tc.result)[:1000] if tc.result else None,
                    "success": tc.success,
                    "error": tc.error,
                }
                for tc in self.tool_calls
            ],
            "response": self.response_text,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
            "success": self.success,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


@dataclass
class JudgeIssue:
    """
    Structured issue feedback from Judge (senior reviewer).

    Provides specific, teachable feedback with code examples.
    Part of the Senior/Junior delegation pattern.
    """

    # Issue severity: minor, major, critical
    severity: str = "major"

    # File where the issue was found
    file: str = ""

    # Line number (if applicable)
    line: int = 0

    # The problematic code snippet
    problem_code: str = ""

    # Explanation of why this is an issue
    explanation: str = ""

    # Suggested fix with code
    suggested_fix: str = ""

    # Educational takeaway for the junior developer
    learning_point: str = ""

    @classmethod
    def from_json(cls, data: Dict[str, Any]) -> "JudgeIssue":
        """Parse JudgeIssue from JSON."""
        return cls(
            severity=data.get("severity", "major"),
            file=data.get("file", ""),
            line=data.get("line", 0),
            problem_code=data.get("problem_code", ""),
            explanation=data.get("explanation", ""),
            suggested_fix=data.get("suggested_fix", ""),
            learning_point=data.get("learning_point", ""),
        )

    def to_json(self) -> Dict[str, Any]:
        """Convert to JSON."""
        return {
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "problem_code": self.problem_code,
            "explanation": self.explanation,
            "suggested_fix": self.suggested_fix,
            "learning_point": self.learning_point,
        }


@dataclass
class RevisionFeedback:
    """Structured feedback for revision requests."""

    # What needs to change
    issues: List[str] = field(default_factory=list)

    # Specific suggestions
    suggestions: List[str] = field(default_factory=list)

    # Files to focus on
    focus_files: List[str] = field(default_factory=list)

    # Whether to retry same approach or try different
    try_different_approach: bool = False


@dataclass
class Judgment:
    """
    Judge's (senior reviewer) evaluation of Executor (junior) output.

    Determines whether to approve, request revision, or reject.
    Includes mentorship feedback with specific code examples.
    """

    # Which execution this judges
    step_id: str

    # The verdict
    verdict: JudgmentVerdict

    # Confidence in the verdict (0.0-1.0)
    confidence: float = 0.8

    # Explanation of judgment
    reasoning: str = ""

    # Criteria that passed
    criteria_passed: List[str] = field(default_factory=list)

    # Criteria that failed
    criteria_failed: List[str] = field(default_factory=list)

    # Feedback for revision (if verdict is REVISE) - legacy format
    revision_feedback: Optional[RevisionFeedback] = None

    # Timestamp
    judged_at: datetime = field(default_factory=datetime.now)

    # Model used
    model: str = ""

    # === Senior/Junior Mentorship Fields ===

    # Positive feedback - what the junior did well (specific, not generic)
    praise: str = ""

    # Structured issues with code examples and learning points
    issues: List[JudgeIssue] = field(default_factory=list)

    # Summary and encouragement for the junior
    overall_feedback: str = ""

    def is_approved(self) -> bool:
        """Check if this is an approval."""
        return self.verdict == JudgmentVerdict.APPROVE

    def needs_revision(self) -> bool:
        """Check if revision is requested."""
        return self.verdict == JudgmentVerdict.REVISE

    def is_rejected(self) -> bool:
        """Check if execution was rejected."""
        return self.verdict == JudgmentVerdict.REJECT

    @classmethod
    def from_json(cls, data: Dict[str, Any], step_id: str) -> "Judgment":
        """Parse Judgment from JSON (LLM output)."""
        verdict_str = data.get("verdict", "approve").lower()
        verdict = {
            "approve": JudgmentVerdict.APPROVE,
            "revise": JudgmentVerdict.REVISE,
            "reject": JudgmentVerdict.REJECT,
        }.get(verdict_str, JudgmentVerdict.APPROVE)

        # Parse legacy revision_feedback format
        revision_feedback = None
        if verdict == JudgmentVerdict.REVISE and "revision_feedback" in data:
            rf = data["revision_feedback"]
            revision_feedback = RevisionFeedback(
                issues=rf.get("issues", []),
                suggestions=rf.get("suggestions", []),
                focus_files=rf.get("focus_files", []),
                try_different_approach=rf.get("try_different_approach", False),
            )

        # Parse new mentorship format issues (list of JudgeIssue)
        issues_data = data.get("issues", [])
        issues = [JudgeIssue.from_json(i) for i in issues_data if isinstance(i, dict)]

        return cls(
            step_id=step_id,
            verdict=verdict,
            confidence=data.get("confidence", 0.8),
            reasoning=data.get("reasoning", ""),
            criteria_passed=data.get("criteria_passed", []),
            criteria_failed=data.get("criteria_failed", []),
            revision_feedback=revision_feedback,
            model=data.get("model", ""),
            # New mentorship fields
            praise=data.get("praise", ""),
            issues=issues,
            overall_feedback=data.get("overall_feedback", ""),
        )

    def to_json(self) -> Dict[str, Any]:
        """Convert to JSON for serialization."""
        result = {
            "step_id": self.step_id,
            "verdict": self.verdict.value,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "criteria_passed": self.criteria_passed,
            "criteria_failed": self.criteria_failed,
            "judged_at": self.judged_at.isoformat(),
            "model": self.model,
            # New mentorship fields
            "praise": self.praise,
            "issues": [issue.to_json() for issue in self.issues],
            "overall_feedback": self.overall_feedback,
        }

        if self.revision_feedback:
            result["revision_feedback"] = {
                "issues": self.revision_feedback.issues,
                "suggestions": self.revision_feedback.suggestions,
                "focus_files": self.revision_feedback.focus_files,
                "try_different_approach": self.revision_feedback.try_different_approach,
            }

        return result
