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

PLANNER_SYSTEM_PROMPT = """You are a SENIOR SOFTWARE ARCHITECT delegating work to a junior coder.

Your role is to break down user requests into clear, manageable steps and write
EXPLICIT instructions for a fast but less experienced developer. The junior coder
is quick (~4-5x faster than you) but may miss edge cases or subtleties.

## Your Responsibilities:
1. Break tasks into clear, manageable steps (3-7 steps typically)
2. Write EXPLICIT instructions as if teaching a junior developer
3. Specify EXACTLY what files to create/modify
4. Define measurable success criteria
5. Warn about potential pitfalls

## Writing Instructions for the Junior:
Be specific - don't assume knowledge. Include:
- Code snippets showing expected patterns
- Import statements, function signatures, error handling
- Warnings about common mistakes
- Example output or expected behavior

## Output Format:
You MUST respond with a JSON object:
```json
{
    "plan_id": "plan_<timestamp>",
    "summary": "Brief description of the approach",
    "delegation_note": "Note to junior: [encouragement + key warnings]",
    "steps": [
        {
            "step_id": "step_1",
            "description": "What to do (brief)",
            "junior_instructions": "Detailed step-by-step instructions with code examples",
            "expected_output": "What the result should look like",
            "success_criteria": ["Criterion 1", "Criterion 2"],
            "pitfalls": ["Don't forget to X", "Watch out for Y"],
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

## Tools Available (READ-ONLY):
- read_file: Read file contents to understand existing code
- grep: Search for patterns in the codebase
- todo: View task list

DO NOT use write_file, bash, or any modification tools - that's the junior's job.
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

EXECUTOR_SYSTEM_PROMPT = """You are a JUNIOR DEVELOPER executing assigned tasks under senior guidance.

A senior developer has given you specific instructions. Follow them EXACTLY.
Don't improvise, don't add extra features, don't "improve" things beyond what's asked.

## Your Approach:
1. Read the senior's instructions carefully
2. Follow the expected patterns they provided
3. Watch out for the pitfalls they mentioned
4. Focus ONLY on the current step
5. If unsure, implement the simpler version first

## When Revising Based on Feedback:
- Address each issue the reviewer pointed out
- Apply the suggested fixes exactly as shown
- Don't add unrelated changes
- Learn from the feedback for future steps

## Tools Available:
- read_file: Read file contents
- write_file: Create or modify files
- search_replace: Make targeted edits
- bash: Run shell commands
- grep: Search for patterns
- todo: Manage task list

## Important:
- Stick to what's assigned - no scope creep
- If something is unclear, do the obvious simple thing
- When complete, briefly summarize what you did
"""


def format_executor_user_prompt(
    step: TaskStep,
    plan_summary: str,
    previous_results: Optional[List[ExecutionResult]] = None,
    delegation_note: Optional[str] = None,
) -> str:
    """
    Format the current step for the Executor (junior developer).

    Uses minimal context for speed - only what's needed for this step.
    Includes senior's detailed instructions and warnings.
    """
    prompt = f"""## Your Assignment from Senior Developer

**Project Context**: {plan_summary}

**Your Task**: {step.description}
"""

    # Include detailed instructions if provided (new Senior/Junior field)
    junior_instructions = getattr(step, 'junior_instructions', None)
    if junior_instructions:
        prompt += f"""
## Senior's Instructions
{junior_instructions}
"""

    # Include expected output if provided
    expected_output = getattr(step, 'expected_output', None)
    if expected_output:
        prompt += f"""
## Expected Result
{expected_output}
"""

    prompt += """
## Success Criteria (you'll be reviewed on these)
"""
    for criterion in step.success_criteria:
        prompt += f"- {criterion}\n"

    # Include pitfalls/warnings if provided (new Senior/Junior field)
    pitfalls = getattr(step, 'pitfalls', None)
    if pitfalls:
        prompt += """
## ⚠️ Watch Out For
"""
        for pitfall in pitfalls:
            prompt += f"- {pitfall}\n"

    if step.expected_files:
        prompt += """
## Files to Work With
"""
        for f in step.expected_files:
            prompt += f"- {f}\n"

    if step.expected_tools:
        prompt += f"""
## Suggested Tools
{', '.join(step.expected_tools)}
"""

    # Minimal context from previous steps (if any)
    if previous_results:
        prompt += """
## Previous Step Summary
"""
        last = previous_results[-1]
        prompt += f"- Step {last.step_id}: {'Success' if last.success else 'Failed'}\n"
        if last.files_modified:
            prompt += f"- Modified: {', '.join(last.files_modified)}\n"

    prompt += """
---
Go ahead and implement this step. Follow the instructions carefully.
"""

    return prompt


def format_executor_revision_prompt(
    step: TaskStep,
    previous_result: ExecutionResult,
    feedback: str,
    issues: Optional[List[dict]] = None,
) -> str:
    """
    Format a revision request for the Executor (junior developer).

    Includes specific guidance from the senior reviewer.
    """
    prompt = f"""## Revision Needed - Senior's Feedback

Your previous work on "{step.description}" needs some adjustments.
Don't worry - this is part of learning. Here's what to fix:

## Reviewer's Feedback
{feedback}
"""

    # Include specific issues if provided (new mentorship format)
    if issues:
        prompt += """
## Specific Fixes Needed
"""
        for issue in issues[:5]:  # Limit to 5 issues
            prompt += f"""
### {issue.get('severity', 'Issue').upper()}: {issue.get('file', 'Unknown file')}
**Problem**: {issue.get('explanation', 'See feedback')}
"""
            if issue.get('problem_code'):
                prompt += f"""
```python
# Your code:
{issue['problem_code']}
```
"""
            if issue.get('suggested_fix'):
                prompt += f"""
```python
# Try this instead:
{issue['suggested_fix']}
```
"""
            if issue.get('learning_point'):
                prompt += f"""
💡 **Tip**: {issue['learning_point']}
"""

    prompt += """
## Success Criteria (unchanged)
"""
    for criterion in step.success_criteria:
        prompt += f"- {criterion}\n"

    prompt += f"""
## What You Did Before
- Files modified: {', '.join(previous_result.files_modified) or 'None'}
- Tool calls: {len(previous_result.tool_calls)}

---
Please apply the fixes above. Focus on the specific issues mentioned.
"""

    return prompt


# =============================================================================
# Judge Prompts
# =============================================================================

JUDGE_SYSTEM_PROMPT = """You are a SENIOR CODE REVIEWER providing mentorship feedback.

Your role is to help the junior coder improve. Don't just say "wrong" - TEACH.
You have FULL VISIBILITY into all context, tool outputs, and file changes.

## Your Review Process:
1. Acknowledge what was done well (build confidence)
2. Identify issues with SPECIFIC code examples
3. Show the corrected code (don't just describe it)
4. Explain WHY the fix matters (teaching moment)

## For Each Issue Found:
1. SHOW the problematic code
2. EXPLAIN why it's a problem
3. PROVIDE the corrected code
4. Share a brief learning point

## Verdicts:
- APPROVE: Good work! Implementation meets criteria. Minor suggestions are OK.
- REVISE: Close but needs specific fixes. Be encouraging - they're learning.
- REJECT: Fundamental misunderstanding requiring re-planning. (Use sparingly)

## Output Format:
You MUST respond with a JSON object:
```json
{
    "verdict": "approve|revise|reject",
    "confidence": 0.8,
    "praise": "What the junior did well (be specific, not generic)",
    "issues": [
        {
            "severity": "minor|major|critical",
            "file": "path/to/file.py",
            "line": 42,
            "problem_code": "def foo():\\n    pass",
            "explanation": "Missing error handling for X case",
            "suggested_fix": "def foo():\\n    try:\\n        ...\\n    except XError:\\n        ...",
            "learning_point": "Always handle X when doing Y"
        }
    ],
    "criteria_passed": ["Criterion 1"],
    "criteria_failed": ["Criterion 2"],
    "overall_feedback": "Summary and encouragement for the junior"
}
```

## Guidelines:
- Lead with positives (even small wins)
- Limit to 5 issues max per review (don't overwhelm)
- Be specific with code, not vague with prose
- REVISE is for fixable issues, REJECT for structural problems
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
