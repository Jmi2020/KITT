"""
Role-specific system prompts for the Tiered Collective Architecture.

Defines the prompts that shape each role's behavior:
- Planner: Strategic architect with read-only tools
- Executor: Implementation role with full tool access
- Judge: Validation role with full context visibility

Context Blinding Pattern (from KITTY graph_async.py):
- Planner/Executor: Receive filtered context (exclude meta/dev tags)
- Judge: Receives FULL context + all tool outputs for complete validation
"""

from typing import List, Optional

from .models import TaskPlan, TaskStep, ExecutionResult


# =============================================================================
# Planner Prompts
# =============================================================================

PLANNER_SYSTEM_PROMPT = """You are a strategic software architect planning task execution.

Your role is to decompose complex user requests into clear, ordered steps that can be
executed by a coding assistant. You create plans, not implementations.

Guidelines:
- Break complex tasks into 3-7 discrete steps
- Each step should be independently verifiable
- Define clear success criteria for each step
- Identify file dependencies between steps
- Estimate complexity (0.0-1.0) for each step
- Consider edge cases and error scenarios

Output Format:
You MUST respond with a JSON object in this exact format:
```json
{
    "plan_id": "plan_<timestamp>",
    "summary": "Brief description of the approach",
    "steps": [
        {
            "step_id": "step_1",
            "description": "What to do",
            "success_criteria": ["Criterion 1", "Criterion 2"],
            "expected_files": ["path/to/file.py"],
            "expected_tools": ["read_file", "write_file"],
            "depends_on": [],
            "complexity": 0.5,
            "optional": false
        }
    ],
    "success_criteria": ["Overall criterion 1"],
    "total_complexity": 0.5,
    "affected_files": ["path/to/file1.py", "path/to/file2.py"]
}
```

Tools Available:
You have access to READ-ONLY tools for exploration:
- read_file: Read file contents
- grep: Search for patterns
- todo: View task list

DO NOT use write_file, bash, or any modification tools.
"""


def format_planner_user_prompt(user_request: str, context: Optional[str] = None) -> str:
    """Format the user request for the Planner."""
    prompt = f"""Please create a task plan for the following request:

<user_request>
{user_request}
</user_request>
"""

    if context:
        prompt += f"""
<additional_context>
{context}
</additional_context>
"""

    prompt += """
Respond with a JSON task plan following the format specified in your system prompt.
Focus on creating clear, verifiable steps that can be executed sequentially.
"""

    return prompt


# =============================================================================
# Executor Prompts
# =============================================================================

EXECUTOR_SYSTEM_PROMPT = """You are a code implementation assistant executing planned tasks.

Your role is to implement the current step exactly as specified. Focus on the immediate
task - do not deviate from the plan or add unplanned features.

Guidelines:
- Execute ONLY the current step
- Follow the success criteria precisely
- Use the expected tools when possible
- Keep implementations minimal and focused
- Report any blockers or issues clearly

You have full access to all tools:
- read_file: Read file contents
- write_file: Create or modify files
- search_replace: Make targeted edits
- bash: Run shell commands
- grep: Search for patterns
- todo: Manage task list

When complete, summarize what was done and any issues encountered.
"""


def format_executor_user_prompt(
    step: TaskStep,
    plan_summary: str,
    previous_results: Optional[List[ExecutionResult]] = None,
) -> str:
    """
    Format the current step for the Executor.

    Uses minimal context for speed - only what's needed for this step.
    """
    prompt = f"""## Current Task

**Plan Summary**: {plan_summary}

**Your Step**: {step.description}

**Success Criteria**:
"""

    for criterion in step.success_criteria:
        prompt += f"- {criterion}\n"

    if step.expected_files:
        prompt += f"""
**Files to Work With**:
"""
        for f in step.expected_files:
            prompt += f"- {f}\n"

    if step.expected_tools:
        prompt += f"""
**Suggested Tools**: {', '.join(step.expected_tools)}
"""

    # Minimal context from previous steps (if any)
    if previous_results:
        prompt += """
**Previous Step Summary**:
"""
        last = previous_results[-1]
        prompt += f"- Step {last.step_id}: {'Success' if last.success else 'Failed'}\n"
        if last.files_modified:
            prompt += f"- Modified: {', '.join(last.files_modified)}\n"

    prompt += """
Execute this step now. Focus only on the current task.
"""

    return prompt


def format_executor_revision_prompt(
    step: TaskStep,
    previous_result: ExecutionResult,
    feedback: str,
) -> str:
    """Format a revision request for the Executor."""
    prompt = f"""## Revision Required

Your previous implementation of step "{step.description}" needs revision.

**Feedback from Review**:
{feedback}

**Original Success Criteria**:
"""

    for criterion in step.success_criteria:
        prompt += f"- {criterion}\n"

    prompt += f"""
**What You Did Previously**:
- Files modified: {', '.join(previous_result.files_modified) or 'None'}
- Tool calls: {len(previous_result.tool_calls)}

Please address the feedback and re-implement this step.
"""

    return prompt


# =============================================================================
# Judge Prompts
# =============================================================================

JUDGE_SYSTEM_PROMPT = """You are a code review judge evaluating implementation quality.

Your role is to validate that the executor's implementation meets the specified criteria.
You have FULL VISIBILITY into all context, tool outputs, and file changes.

Evaluation Process:
1. Review the original step requirements
2. Examine all tool calls and their results
3. Check files that were modified
4. Verify each success criterion
5. Make a judgment

Verdicts:
- APPROVE: Implementation meets all criteria, ready to proceed
- REVISE: Implementation is close but needs specific improvements
- REJECT: Implementation is fundamentally wrong, needs re-planning

Output Format:
You MUST respond with a JSON object:
```json
{
    "verdict": "approve|revise|reject",
    "confidence": 0.8,
    "reasoning": "Explanation of your judgment",
    "criteria_passed": ["Criterion 1"],
    "criteria_failed": ["Criterion 2"],
    "revision_feedback": {
        "issues": ["Issue 1"],
        "suggestions": ["Suggestion 1"],
        "focus_files": ["file.py"],
        "try_different_approach": false
    }
}
```

Note: revision_feedback is only required if verdict is "revise".

Be thorough but fair. Minor issues should lead to REVISE, not REJECT.
REJECT is reserved for fundamental problems requiring a different approach.
"""


def format_judge_user_prompt(
    plan: TaskPlan,
    step: TaskStep,
    execution_result: ExecutionResult,
    file_diffs: Optional[str] = None,
) -> str:
    """
    Format the full context for the Judge.

    Judge gets COMPLETE visibility (context blinding pattern from KITTY).
    """
    prompt = f"""## Review Request

**Plan Summary**: {plan.summary}

**Step Being Reviewed**: {step.description}

**Success Criteria**:
"""

    for criterion in step.success_criteria:
        prompt += f"- {criterion}\n"

    prompt += """
---

## Execution Details

**Tool Calls Made**:
"""

    for tc in execution_result.tool_calls:
        prompt += f"""
### {tc.tool_name}
- Arguments: {tc.arguments}
- Success: {tc.success}
- Duration: {tc.duration_ms}ms
"""
        if tc.error:
            prompt += f"- Error: {tc.error}\n"
        if tc.result:
            result_str = str(tc.result)
            if len(result_str) > 500:
                result_str = result_str[:500] + "..."
            prompt += f"- Result: {result_str}\n"

    prompt += f"""
**Executor's Response**:
{execution_result.response_text}

**Files Modified**: {', '.join(execution_result.files_modified) or 'None'}
**Files Created**: {', '.join(execution_result.files_created) or 'None'}
**Execution Time**: {execution_result.duration_ms}ms
"""

    if file_diffs:
        prompt += f"""
---

## File Diffs

```diff
{file_diffs}
```
"""

    prompt += """
---

Please evaluate this implementation and provide your judgment in JSON format.
"""

    return prompt


# =============================================================================
# Context Filtering
# =============================================================================

def filter_context_for_executor(full_context: str) -> str:
    """
    Filter context for Executor (context blinding).

    Removes meta tags, developer notes, and system information
    that could confuse or distract the Executor.
    """
    import re

    # Remove XML-style meta tags
    filtered = re.sub(r'<meta[^>]*>.*?</meta>', '', full_context, flags=re.DOTALL)
    filtered = re.sub(r'<dev-notes?>.*?</dev-notes?>', '', filtered, flags=re.DOTALL)
    filtered = re.sub(r'<system-info>.*?</system-info>', '', filtered, flags=re.DOTALL)

    # Remove markdown-style developer comments
    filtered = re.sub(r'<!--\s*DEV:.*?-->', '', filtered, flags=re.DOTALL)

    # Clean up extra whitespace
    filtered = re.sub(r'\n{3,}', '\n\n', filtered)

    return filtered.strip()


def prepare_judge_context(
    plan: TaskPlan,
    step: TaskStep,
    execution_result: ExecutionResult,
    conversation_history: Optional[str] = None,
) -> str:
    """
    Prepare full context for Judge (no filtering).

    Judge gets everything for complete validation.
    """
    context = format_judge_user_prompt(plan, step, execution_result)

    if conversation_history:
        context += f"""
---

## Full Conversation Context

{conversation_history}
"""

    return context
