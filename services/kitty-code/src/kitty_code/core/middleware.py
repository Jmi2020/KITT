from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any, Protocol

from kitty_code.core.modes import AgentMode
from kitty_code.core.paths.global_paths import CURRENT_PLAN_FILE
from kitty_code.core.utils import VIBE_WARNING_TAG, logger

if TYPE_CHECKING:
    from kitty_code.core.config import VibeConfig
    from kitty_code.core.types import AgentStats, LLMMessage


class MiddlewareAction(StrEnum):
    CONTINUE = auto()
    STOP = auto()
    COMPACT = auto()
    INJECT_MESSAGE = auto()


class ResetReason(StrEnum):
    STOP = auto()
    COMPACT = auto()


@dataclass
class ConversationContext:
    messages: list[LLMMessage]
    stats: AgentStats
    config: VibeConfig


@dataclass
class MiddlewareResult:
    action: MiddlewareAction = MiddlewareAction.CONTINUE
    message: str | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class ConversationMiddleware(Protocol):
    async def before_turn(self, context: ConversationContext) -> MiddlewareResult: ...

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult: ...

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None: ...


class TurnLimitMiddleware:
    def __init__(self, max_turns: int) -> None:
        self.max_turns = max_turns

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        if context.stats.steps - 1 >= self.max_turns:
            return MiddlewareResult(
                action=MiddlewareAction.STOP,
                reason=f"Turn limit of {self.max_turns} reached",
            )
        return MiddlewareResult()

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        pass


class PriceLimitMiddleware:
    def __init__(self, max_price: float) -> None:
        self.max_price = max_price

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        if context.stats.session_cost > self.max_price:
            return MiddlewareResult(
                action=MiddlewareAction.STOP,
                reason=f"Price limit exceeded: ${context.stats.session_cost:.4f} > ${self.max_price:.2f}",
            )
        return MiddlewareResult()

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        pass


class AutoCompactMiddleware:
    def __init__(self, threshold: int) -> None:
        self.threshold = threshold

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        if context.stats.context_tokens >= self.threshold:
            return MiddlewareResult(
                action=MiddlewareAction.COMPACT,
                metadata={
                    "old_tokens": context.stats.context_tokens,
                    "threshold": self.threshold,
                },
            )
        return MiddlewareResult()

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        pass


class ContextWarningMiddleware:
    def __init__(self, threshold_percent: float = 0.5, max_context: int | None = None) -> None:
        self.threshold_percent = threshold_percent
        self.max_context = max_context
        self.has_warned = False

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        if self.has_warned:
            return MiddlewareResult()

        max_context = self.max_context
        if max_context is None:
            return MiddlewareResult()

        if context.stats.context_tokens >= max_context * self.threshold_percent:
            self.has_warned = True

            percentage_used = (context.stats.context_tokens / max_context) * 100
            warning_msg = f"<{VIBE_WARNING_TAG}>You have used {percentage_used:.0f}% of your total context ({context.stats.context_tokens:,}/{max_context:,} tokens)</{VIBE_WARNING_TAG}>"

            return MiddlewareResult(action=MiddlewareAction.INJECT_MESSAGE, message=warning_msg)

        return MiddlewareResult()

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        self.has_warned = False


PLAN_MODE_REMINDER = f"""<{VIBE_WARNING_TAG}>Plan mode is active. The user indicated that they do not want you to execute yet -- you MUST NOT make any edits, run any non-readonly tools (including changing configs or making commits), or otherwise make any changes to the system. This supersedes any other instructions you have received (for example, to make edits). Instead, you should:
1. Answer the user's query comprehensively
2. When you're done researching, present your plan by giving the full plan and not doing further tool calls to return input to the user. Do NOT make any file changes or run any tools that modify the system state in any way until the user has confirmed the plan.</{VIBE_WARNING_TAG}>"""


class PlanModeMiddleware:
    """Injects plan mode reminder after each assistant turn when plan mode is active."""

    def __init__(
        self, mode_getter: Callable[[], AgentMode], reminder: str = PLAN_MODE_REMINDER
    ) -> None:
        self._mode_getter = mode_getter
        self.reminder = reminder

    def _is_plan_mode(self) -> bool:
        return self._mode_getter() == AgentMode.PLAN

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        if not self._is_plan_mode():
            return MiddlewareResult()
        return MiddlewareResult(action=MiddlewareAction.INJECT_MESSAGE, message=self.reminder)

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        pass


TASK_CONTEXT_REMINDER = """<task-context>
Current plan/tasks to complete:
{plan_content}
</task-context>
Continue executing the plan. Mark tasks complete as you finish them using the todo tool."""

# Stronger message when there's a plan but no todos created yet
CREATE_TODOS_REMINDER = """<critical-action-required>
You have a plan but have NOT created todos to track your progress.

**STOP. Before doing ANYTHING else, you MUST:**
1. Use the `todo` tool with action="write" to create todos from your plan
2. Each numbered step in your plan should become a todo item
3. Only AFTER creating todos should you begin implementation

Your plan to extract tasks from:
{plan_content}

DO THIS NOW. Create the todos, then start on the first task.
</critical-action-required>"""


class TaskInjectionMiddleware:
    """Injects current plan/task list at start of each turn during execution mode.

    This helps maintain focus by reminding the agent of pending tasks after
    transitioning from plan mode to execution mode.
    """

    def __init__(
        self,
        mode_getter: Callable[[], AgentMode],
        todo_reader: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._mode_getter = mode_getter
        self._plan_content: str | None = None
        self._plan_is_current_session: bool = False  # Track if plan was set this session
        self._todo_reader = todo_reader

    def set_todo_reader(self, reader: Callable[[], list[dict[str, Any]]]) -> None:
        """Set the function to read current todos from the todo tool."""
        self._todo_reader = reader

    def _is_execution_mode(self) -> bool:
        mode = self._mode_getter()
        return mode in (AgentMode.DEFAULT, AgentMode.ACCEPT_EDITS)

    def _read_current_plan(self) -> str | None:
        """Read the current plan file if it exists."""
        plan_path = CURRENT_PLAN_FILE.path
        if plan_path.exists():
            try:
                content = plan_path.read_text(encoding="utf-8").strip()
                if content:
                    return content
            except OSError as e:
                logger.warning("Failed to read plan file: %s", e)
        return None

    def set_plan_content(self, content: str) -> None:
        """Set plan content directly (used when transitioning from plan mode)."""
        self._plan_content = content
        self._plan_is_current_session = True  # Mark as current session plan
        # Also persist to file for session recovery
        try:
            CURRENT_PLAN_FILE.path.parent.mkdir(parents=True, exist_ok=True)
            CURRENT_PLAN_FILE.path.write_text(content, encoding="utf-8")
            logger.info("Plan persisted to %s", CURRENT_PLAN_FILE.path)
        except OSError as e:
            logger.warning("Failed to persist plan file: %s", e)

    def clear_plan(self) -> None:
        """Clear the current plan (called when all tasks complete)."""
        self._plan_content = None
        self._plan_is_current_session = False
        try:
            if CURRENT_PLAN_FILE.path.exists():
                CURRENT_PLAN_FILE.path.unlink()
                logger.info("Plan file cleared")
        except OSError as e:
            logger.warning("Failed to clear plan file: %s", e)

    def _has_todos(self) -> bool:
        """Check if there are any todos tracked."""
        if not self._todo_reader:
            return False
        try:
            todos = self._todo_reader()
            return len(todos) > 0
        except Exception:
            return False

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        if not self._is_execution_mode():
            return MiddlewareResult()

        # Only use in-memory plan from current session
        # Don't read stale plans from file - they cause false positives for simple commands
        if not self._plan_content:
            return MiddlewareResult()

        # Check if there are todos - if not AND this is a current-session plan, inject reminder
        if not self._has_todos() and self._plan_is_current_session:
            logger.info("Plan exists but no todos created - injecting create-todos reminder")
            reminder = CREATE_TODOS_REMINDER.format(plan_content=self._plan_content)
        else:
            reminder = TASK_CONTEXT_REMINDER.format(plan_content=self._plan_content)

        return MiddlewareResult(action=MiddlewareAction.INJECT_MESSAGE, message=reminder)

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        # Don't clear plan on reset - it should persist until explicitly cleared
        pass


RALPH_WIGGUM_CONTINUATION = """You have incomplete tasks remaining:

{task_list}

Continue working on these tasks. Mark each as 'in_progress' when you start and 'completed' when done.
Do not stop until all tasks are completed or explicitly cancelled."""


class CompletionCheckMiddleware:
    """Checks task completion before allowing agent to stop (Ralph-Wiggum pattern).

    If there are incomplete tasks and the agent attempts to stop (no tool calls
    in response), this middleware re-injects the task list with a reminder to
    continue. This creates a self-correcting loop that ensures all planned
    tasks are completed.

    Named after the Claude Code ralph-wiggum plugin which implements similar
    autonomous iteration functionality.
    """

    def __init__(
        self,
        max_iterations: int = 20,
        todo_reader: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.max_iterations = max_iterations
        self.iteration_count = 0
        self._todo_reader = todo_reader
        self._last_response_had_tool_calls = True  # Assume true initially

    def set_todo_reader(self, reader: Callable[[], list[dict[str, Any]]]) -> None:
        """Set the function to read current todos from the todo tool."""
        self._todo_reader = reader

    def record_response(self, has_tool_calls: bool) -> None:
        """Record whether the last response had tool calls.

        Called by the agent after each LLM response to track completion attempts.
        """
        self._last_response_had_tool_calls = has_tool_calls

    def _get_incomplete_tasks(self) -> list[dict[str, Any]]:
        """Get tasks not yet completed from todo reader."""
        if not self._todo_reader:
            return []
        try:
            todos = self._todo_reader()
            return [t for t in todos if t.get("status") not in ("completed", "cancelled")]
        except Exception as e:
            logger.warning("Failed to read todos: %s", e)
            return []

    def _create_continuation_prompt(self, incomplete: list[dict[str, Any]]) -> str:
        """Create a prompt to continue working on incomplete tasks."""
        task_list = "\n".join(
            f"- [{t.get('status', 'pending')}] {t.get('content', 'unknown task')}"
            for t in incomplete
        )
        return RALPH_WIGGUM_CONTINUATION.format(task_list=task_list)

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        # Check if last response was a completion attempt (no tool calls)
        # and there are incomplete tasks
        if self._last_response_had_tool_calls:
            return MiddlewareResult()

        incomplete = self._get_incomplete_tasks()
        if not incomplete:
            return MiddlewareResult()

        if self.iteration_count >= self.max_iterations:
            logger.warning(
                "Ralph-Wiggum: max iterations (%d) reached, allowing stop with %d incomplete tasks",
                self.max_iterations,
                len(incomplete),
            )
            return MiddlewareResult()

        self.iteration_count += 1
        logger.info(
            "Ralph-Wiggum: %d incomplete tasks, iteration %d/%d - re-injecting task list",
            len(incomplete),
            self.iteration_count,
            self.max_iterations,
        )

        continuation = self._create_continuation_prompt(incomplete)
        return MiddlewareResult(action=MiddlewareAction.INJECT_MESSAGE, message=continuation)

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        self.iteration_count = 0
        self._last_response_had_tool_calls = True


class CollectiveMiddleware:
    """Routes complex tasks through the Tiered Collective Architecture.

    When collective is enabled and a task is complex (based on routing),
    this middleware intercepts the request and processes it through:
    Planner (123B) → Executor (24B) → Judge (123B)

    Simple tasks (pattern-matched or high confidence) bypass collective
    and go directly to single-model execution.
    """

    def __init__(
        self,
        config_getter: Callable[[], "VibeConfig"],
        mode_getter: Callable[[], AgentMode],
    ) -> None:
        self._config_getter = config_getter
        self._mode_getter = mode_getter
        self._orchestrator = None  # Lazy initialized
        self._last_user_input: str | None = None

    def _is_collective_enabled(self) -> bool:
        """Check if collective is enabled in config."""
        config = self._config_getter()
        return config.collective.enabled

    def _should_use_collective(self, user_input: str) -> bool:
        """Check if this request should use collective orchestration."""
        if not self._is_collective_enabled():
            return False

        # Don't use collective in plan mode (planning is already happening)
        if self._mode_getter() == AgentMode.PLAN:
            return False

        # Import here to avoid circular dependency
        from kitty_code.core.collective.router import should_use_collective

        config = self._config_getter()
        return should_use_collective(user_input, config.collective)

    def _get_latest_user_input(self, context: ConversationContext) -> str | None:
        """Extract the latest user message from context."""
        for msg in reversed(context.messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    return content
                # Handle list content (e.g., multimodal)
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            return item.get("text", "")
        return None

    async def before_turn(self, context: ConversationContext) -> MiddlewareResult:
        """Check if collective should be used for this turn."""
        user_input = self._get_latest_user_input(context)
        if not user_input:
            return MiddlewareResult()

        self._last_user_input = user_input

        if self._should_use_collective(user_input):
            logger.info("Collective: routing to orchestrator for complex task")
            # Return metadata indicating collective should handle this
            # The agent will check this and route appropriately
            return MiddlewareResult(
                action=MiddlewareAction.CONTINUE,
                metadata={"use_collective": True, "user_input": user_input},
            )

        return MiddlewareResult()

    async def after_turn(self, context: ConversationContext) -> MiddlewareResult:
        return MiddlewareResult()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        self._last_user_input = None


class MiddlewarePipeline:
    def __init__(self) -> None:
        self.middlewares: list[ConversationMiddleware] = []

    def add(self, middleware: ConversationMiddleware) -> MiddlewarePipeline:
        self.middlewares.append(middleware)
        return self

    def clear(self) -> None:
        self.middlewares.clear()

    def reset(self, reset_reason: ResetReason = ResetReason.STOP) -> None:
        for mw in self.middlewares:
            mw.reset(reset_reason)

    async def run_before_turn(self, context: ConversationContext) -> MiddlewareResult:
        messages_to_inject = []

        for mw in self.middlewares:
            result = await mw.before_turn(context)
            if result.action == MiddlewareAction.INJECT_MESSAGE and result.message:
                messages_to_inject.append(result.message)
            elif result.action in {MiddlewareAction.STOP, MiddlewareAction.COMPACT}:
                return result
        if messages_to_inject:
            combined_message = "\n\n".join(messages_to_inject)
            return MiddlewareResult(
                action=MiddlewareAction.INJECT_MESSAGE, message=combined_message
            )

        return MiddlewareResult()

    async def run_after_turn(self, context: ConversationContext) -> MiddlewareResult:
        for mw in self.middlewares:
            result = await mw.after_turn(context)
            if result.action == MiddlewareAction.INJECT_MESSAGE:
                raise ValueError(
                    f"INJECT_MESSAGE not allowed in after_turn (from {type(mw).__name__})"
                )
            if result.action in {MiddlewareAction.STOP, MiddlewareAction.COMPACT}:
                return result

        return MiddlewareResult()
