# noqa: D401
"""Core orchestration logic for conversational device control."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

from common.credentials import HomeAssistantCredentials
from common.db.models import RoutingTier
from common.config import settings

from .memory import MemoryClient
from .models.context import ConversationContext, DeviceSelection
from .routing.router import BrainRouter, RoutingRequest, RoutingResult
from .routing.vision_policy import analyze_prompt
from .routing.freshness import is_time_sensitive_query
from .skills.home_assistant import HomeAssistantSkill
from .state.mqtt_context_store import MQTTContextStore
from .conversation.state import ConversationStateManager
from .conversation.safety import SafetyChecker
from .agents.graphs.integration import LangGraphRoutingIntegration


logger = logging.getLogger("brain.orchestrator")


class BrainOrchestrator:
    """Coordinate conversation context updates and device skill execution."""

    _HAZARD_INTENTS = {
        "lock.unlock": "unlock",
        "power.enable": "power_enable",
    }

    def __init__(
        self,
        context_store: MQTTContextStore,
        ha_credentials: HomeAssistantCredentials,
        router: BrainRouter,
        safety_workflow: Any | None = None,
        memory_client: MemoryClient | None = None,
        langgraph_integration: Optional[LangGraphRoutingIntegration] = None,
        state_manager: Any | None = None,
    ) -> None:
        self._context_store = context_store
        self._ha_skill = HomeAssistantSkill(ha_credentials)
        self._router = router
        self._safety = safety_workflow
        self._memory = memory_client or MemoryClient()
        self._langgraph = langgraph_integration

        # Initialize conversation state manager for multi-turn workflows
        # Use provided manager (persistent) or fallback to in-memory
        self._state_manager = state_manager or ConversationStateManager()

        # Initialize safety checker for confirmation phrase verification
        self._safety_checker = SafetyChecker()

        if self._langgraph and self._langgraph.enabled:
            logger.info(
                f"BrainOrchestrator initialized with LangGraph routing "
                f"(rollout: {self._langgraph.rollout_percent}%)"
            )
        else:
            logger.info("BrainOrchestrator initialized with traditional routing")

    async def handle_device_intent(
        self,
        conversation_id: str,
        intent: str,
        payload: Dict[str, Any],
        device: Dict[str, Any] | None,
    ) -> Dict[str, Any]:
        context = self._context_store.get_context(conversation_id) or ConversationContext(
            conversation_id=conversation_id
        )
        context.last_intent = intent
        if device:
            context.device = DeviceSelection(**device)
        self._context_store.set_context(context)

        hazard_key = self._HAZARD_INTENTS.get(intent)
        if hazard_key and self._safety:
            signature = payload.get("signature")
            zone_id = context.device.zone_id if context.device else None
            allowed, response = await self._safety.process_device_intent(
                intent=hazard_key,
                device_id=context.device.device_id if context.device else None,
                zone_id=zone_id,
                user_id=payload.get("initiatedBy", "unknown"),
                signature=signature,
            )
            if not allowed:
                return response

        return await self._ha_skill.execute(context, intent, payload)

    async def generate_response(
        self,
        conversation_id: str,
        request_id: str,
        prompt: str,
        *,
        user_id: str | None = None,
        force_tier: RoutingTier | None = None,
        freshness_required: bool = False,
        model_hint: str | None = None,
        use_agent: bool = False,
        tool_mode: str = "auto",
    ) -> RoutingResult:
        # Get or create conversation state
        conv_state = self._state_manager.get_or_create(conversation_id, user_id or "unknown")
        # Handle case where sync wrapper returns a Task in async context
        if hasattr(conv_state, '__await__'):
            conv_state = await conv_state

        # Check for expired confirmations
        if conv_state.is_confirmation_expired():
            logger.warning(f"Pending confirmation expired for conversation {conversation_id}")
            conv_state.clear_pending_confirmation()

        # Check if there's a pending confirmation
        if conv_state.has_pending_confirmation():
            pending = conv_state.pending_confirmation
            required_phrase = pending["confirmation_phrase"]

            # Check if user provided confirmation
            if self._safety_checker.verify_confirmation(prompt, required_phrase):
                logger.info(f"Confirmation verified for {pending['tool_name']}")

                # Clear pending confirmation and execute the tool
                conv_state.clear_pending_confirmation()

                # Re-route with the confirmed tool execution
                # Set a flag to indicate confirmation was provided
                cleaned_prompt = f"Execute confirmed action: {pending['tool_name']}"
                allow_paid = True  # Confirmation implies approval

            elif prompt.strip().lower() in {"cancel", "abort", "no", "stop"}:
                # User cancelled the action
                logger.info(f"User cancelled pending confirmation for {pending['tool_name']}")
                conv_state.clear_pending_confirmation()

                return RoutingResult(
                    output=f"Action cancelled: {pending['tool_name']} was not executed.",
                    confidence=1.0,
                    tier=RoutingTier.local,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    cost_usd=0.0,
                    latency_ms=0,
                )

            else:
                # User said something else while confirmation is pending
                # Re-display the confirmation message
                confirmation_msg = self._safety_checker.get_confirmation_message(
                    pending["tool_name"],
                    pending["tool_args"],
                    required_phrase,
                    pending["reason"],
                )

                return RoutingResult(
                    output=f"{confirmation_msg}\n\n(Or say 'cancel' to abort)",
                    confidence=1.0,
                    tier=RoutingTier.local,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    cost_usd=0.0,
                    latency_ms=0,
                )

        override_token = os.getenv("API_OVERRIDE_PASSWORD", "omega") or ""
        allow_paid = False
        cleaned_prompt = prompt
        if override_token:
            token_pattern = re.compile(rf"\b{re.escape(override_token)}\b", re.IGNORECASE)
            if token_pattern.search(prompt):
                allow_paid = True
                cleaned_prompt = token_pattern.sub("", prompt).strip()

        # Retrieve relevant memories
        enriched_prompt = cleaned_prompt
        try:
            memories = await self._memory.search_memories(
                query=cleaned_prompt,
                conversation_id=conversation_id,
                user_id=user_id,
                limit=3,
                score_threshold=0.75,
            )
            if not memories and user_id:
                memories = await self._memory.search_memories(
                    query=prompt,
                    conversation_id=None,
                    user_id=user_id,
                    limit=3,
                    score_threshold=0.7,
                )
            if memories:
                memory_context = "\n".join(
                    [f"[Memory {i+1}]: {m.content}" for i, m in enumerate(memories)]
                )
                enriched_prompt = (
                    f"<relevant_context>\n{memory_context}\n</relevant_context>\n\n" f"{cleaned_prompt}"
                )
        except Exception:
            # If memory service is unavailable, continue without memories
            pass

        agentic_mode = use_agent or settings.agentic_mode_enabled

        time_sensitive = is_time_sensitive_query(prompt)
        requires_fresh = freshness_required or time_sensitive

        vision_plan = analyze_prompt(cleaned_prompt)
        logger.info(
            "Vision plan: should=%s targets=%s",
            vision_plan.should_suggest,
            ", ".join(vision_plan.targets) if vision_plan.targets else "—",
        )
        routing_request = RoutingRequest(
            conversation_id=conversation_id,
            request_id=request_id,
            prompt=enriched_prompt,
            user_id=user_id,
            force_tier=force_tier,
            freshness_required=requires_fresh,
            model_hint=model_hint,
            use_agent=agentic_mode,
            tool_mode=tool_mode,
            allow_paid=allow_paid,
            vision_targets=vision_plan.targets if vision_plan.should_suggest else None,
        )

        # Check if LangGraph routing should be used
        if self._langgraph and await self._langgraph.should_use_langgraph(routing_request):
            logger.info("Using LangGraph routing for this request")
            try:
                result = await self._langgraph.route_with_langgraph(routing_request)
            except Exception as exc:
                logger.error(f"LangGraph routing failed, falling back to traditional: {exc}")
                result = await self._router.route(routing_request)
        else:
            result = await self._router.route(routing_request)

        # Store the interaction as a new memory
        try:
            memory_content = f"User: {prompt}\nAssistant: {result.output}"
            await self._memory.add_memory(
                conversation_id=conversation_id,
                content=memory_content,
                user_id=user_id,
                metadata={
                    "request_id": request_id,
                    "tier": result.tier.value,
                    "confidence": result.confidence,
                },
            )
        except Exception:
            # If memory storage fails, log but don't fail the request
            pass

        return result

    async def generate_response_stream(
        self,
        conversation_id: str,
        request_id: str,
        prompt: str,
        *,
        user_id: str | None = None,
        force_tier: RoutingTier | None = None,
        freshness_required: bool = False,
        model_hint: str | None = None,
        use_agent: bool = False,
        tool_mode: str = "auto",
    ):
        """Generate streaming response with real-time thinking traces.

        Yields chunks in format:
        {
            "delta": str,              # Content delta
            "delta_thinking": str,     # Thinking trace delta (optional)
            "done": bool,              # Whether stream is complete
            "routing_result": RoutingResult  # Final result (only when done=True)
        }

        Note: For queries requiring tool execution (freshness_required, agentic mode),
        this falls back to non-streaming to ensure proper tool execution and answer synthesis.
        """
        # Check if query requires agent mode (tool execution)
        # Streaming doesn't support agent/tool execution, so fall back to non-streaming
        agentic_mode = use_agent or settings.agentic_mode_enabled
        time_sensitive = is_time_sensitive_query(prompt)
        requires_agent = agentic_mode and (freshness_required or time_sensitive)

        if requires_agent:
            logger.info("Query requires agent mode - falling back to non-streaming for tool execution")
            # Use non-streaming route which supports agent/tool execution
            result = await self.generate_response(
                conversation_id=conversation_id,
                request_id=request_id,
                prompt=prompt,
                user_id=user_id,
                force_tier=force_tier,
                freshness_required=freshness_required,
                model_hint=model_hint,
                use_agent=use_agent,
                tool_mode=tool_mode,
            )
            # Yield the complete result as a single chunk
            yield {
                "delta": result.output,
                "delta_thinking": None,
                "done": True,
                "routing_result": result,
            }
            return

        # Get or create conversation state
        conv_state = self._state_manager.get_or_create(conversation_id, user_id or "unknown")
        # Handle case where sync wrapper returns a Task in async context
        if hasattr(conv_state, '__await__'):
            conv_state = await conv_state

        # Check for expired confirmations
        if conv_state.is_confirmation_expired():
            logger.warning(f"Pending confirmation expired for conversation {conversation_id}")
            conv_state.clear_pending_confirmation()

        # Check if there's a pending confirmation
        if conv_state.has_pending_confirmation():
            pending = conv_state.pending_confirmation
            required_phrase = pending["confirmation_phrase"]

            # Check if user provided confirmation
            if self._safety_checker.verify_confirmation(prompt, required_phrase):
                logger.info(f"Confirmation verified for {pending['tool_name']}")

                # Clear pending confirmation and execute the tool
                conv_state.clear_pending_confirmation()

                # Re-route with the confirmed tool execution
                # Set a flag to indicate confirmation was provided
                cleaned_prompt = f"Execute confirmed action: {pending['tool_name']}"
                allow_paid = True  # Confirmation implies approval

            elif prompt.strip().lower() in {"cancel", "abort", "no", "stop"}:
                # User cancelled the action
                logger.info(f"User cancelled pending confirmation for {pending['tool_name']}")
                conv_state.clear_pending_confirmation()

                result = RoutingResult(
                    output=f"Action cancelled: {pending['tool_name']} was not executed.",
                    confidence=1.0,
                    tier=RoutingTier.local,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    cost_usd=0.0,
                    latency_ms=0,
                )
                yield {
                    "delta": result.output,
                    "delta_thinking": None,
                    "done": True,
                    "routing_result": result,
                }
                return

            else:
                # User said something else while confirmation is pending
                # Re-display the confirmation message
                confirmation_msg = self._safety_checker.get_confirmation_message(
                    pending["tool_name"],
                    pending["tool_args"],
                    required_phrase,
                    pending["reason"],
                )

                result = RoutingResult(
                    output=f"{confirmation_msg}\n\n(Or say 'cancel' to abort)",
                    confidence=1.0,
                    tier=RoutingTier.local,
                    request_id=request_id,
                    conversation_id=conversation_id,
                    cost_usd=0.0,
                    latency_ms=0,
                )
                yield {
                    "delta": result.output,
                    "delta_thinking": None,
                    "done": True,
                    "routing_result": result,
                }
                return

        override_token = os.getenv("API_OVERRIDE_PASSWORD", "omega") or ""
        allow_paid = False
        cleaned_prompt = prompt
        if override_token:
            token_pattern = re.compile(rf"\b{re.escape(override_token)}\b", re.IGNORECASE)
            if token_pattern.search(prompt):
                allow_paid = True
                cleaned_prompt = token_pattern.sub("", prompt).strip()

        # Retrieve relevant memories
        enriched_prompt = cleaned_prompt
        try:
            memories = await self._memory.search_memories(
                query=cleaned_prompt,
                conversation_id=conversation_id,
                user_id=user_id,
                limit=3,
                score_threshold=0.75,
            )
            if not memories and user_id:
                memories = await self._memory.search_memories(
                    query=prompt,
                    conversation_id=None,
                    user_id=user_id,
                    limit=3,
                    score_threshold=0.7,
                )
            if memories:
                memory_context = "\n".join(
                    [f"[Memory {i+1}]: {m.content}" for i, m in enumerate(memories)]
                )
                enriched_prompt = (
                    f"<relevant_context>\n{memory_context}\n</relevant_context>\n\n" f"{cleaned_prompt}"
                )
        except Exception:
            # If memory service is unavailable, continue without memories
            pass

        agentic_mode = use_agent or settings.agentic_mode_enabled

        time_sensitive = is_time_sensitive_query(prompt)
        requires_fresh = freshness_required or time_sensitive

        vision_plan = analyze_prompt(cleaned_prompt)
        logger.info(
            "Vision plan: should=%s targets=%s",
            vision_plan.should_suggest,
            ", ".join(vision_plan.targets) if vision_plan.targets else "—",
        )
        routing_request = RoutingRequest(
            conversation_id=conversation_id,
            request_id=request_id,
            prompt=enriched_prompt,
            user_id=user_id,
            force_tier=force_tier,
            freshness_required=requires_fresh,
            model_hint=model_hint,
            use_agent=agentic_mode,
            tool_mode=tool_mode,
            allow_paid=allow_paid,
            vision_targets=vision_plan.targets if vision_plan.should_suggest else None,
        )

        # Accumulate full response for memory storage
        full_content = ""
        final_result = None

        # Check if LangGraph routing should be used
        if self._langgraph and await self._langgraph.should_use_langgraph(routing_request):
            logger.info("Using LangGraph routing for streaming (not yet supported, falling back)")
            # LangGraph streaming not implemented yet, fall back to traditional
            async for chunk in self._router.route_stream(routing_request):
                if chunk.get("delta"):
                    full_content += chunk["delta"]
                if chunk.get("done") and chunk.get("routing_result"):
                    final_result = chunk["routing_result"]
                yield chunk
        else:
            async for chunk in self._router.route_stream(routing_request):
                if chunk.get("delta"):
                    full_content += chunk["delta"]
                if chunk.get("done") and chunk.get("routing_result"):
                    final_result = chunk["routing_result"]
                yield chunk

        # Store the interaction as a new memory
        if final_result:
            try:
                memory_content = f"User: {prompt}\nAssistant: {full_content}"
                await self._memory.add_memory(
                    conversation_id=conversation_id,
                    content=memory_content,
                    user_id=user_id,
                    metadata={
                        "request_id": request_id,
                        "tier": final_result.tier.value,
                        "confidence": final_result.confidence,
                    },
                )
            except Exception:
                # If memory storage fails, log but don't fail the request
                pass

    async def set_pending_confirmation(
        self,
        conversation_id: str,
        user_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        confirmation_phrase: str,
        hazard_class: str,
        reason: str,
    ) -> None:
        """Set a pending confirmation for a conversation.

        Args:
            conversation_id: Conversation identifier
            user_id: User identifier
            tool_name: Tool requiring confirmation
            tool_args: Tool arguments
            confirmation_phrase: Required confirmation phrase
            hazard_class: Hazard classification
            reason: Reason for confirmation requirement
        """
        conv_state = self._state_manager.get_or_create(conversation_id, user_id)
        # Handle case where sync wrapper returns a Task in async context
        if hasattr(conv_state, '__await__'):
            conv_state = await conv_state
        conv_state.set_pending_confirmation(
            tool_name=tool_name,
            tool_args=tool_args,
            confirmation_phrase=confirmation_phrase,
            hazard_class=hazard_class,
            reason=reason,
        )
        logger.info(
            f"Set pending confirmation for {tool_name} in conversation {conversation_id}"
        )

    def get_conversation_state(self, conversation_id: str):
        """Get conversation state for a conversation ID."""
        return self._state_manager.get(conversation_id)

    def clear_pending_confirmation(self, conversation_id: str) -> bool:
        """Clear any pending confirmation for a conversation.

        Args:
            conversation_id: Conversation identifier

        Returns:
            True if a confirmation was cleared, False otherwise
        """
        conv_state = self._state_manager.get(conversation_id)
        if conv_state and conv_state.has_pending_confirmation():
            conv_state.clear_pending_confirmation()
            logger.info(f"Cleared pending confirmation for conversation {conversation_id}")
            return True
        return False


__all__ = ["BrainOrchestrator"]
