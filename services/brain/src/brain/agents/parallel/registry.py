"""
Agent and endpoint registry for parallel orchestration.

Defines:
- ModelEndpoint: LLM server configuration with slot tracking
- KittyAgent: Specialized agent definitions with model routing
- ENDPOINTS: Global endpoint registry matching infrastructure
- KITTY_AGENTS: Full agent registry for KITTY

Endpoints are configured from environment variables to match
ops/scripts/llama/start.sh and docker-compose services.
"""

import asyncio
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .types import ModelTier


@dataclass
class ModelEndpoint:
    """
    Endpoint configuration with runtime slot tracking.

    Each endpoint represents a llama.cpp or Ollama server with
    a fixed number of concurrent inference slots.

    Attributes:
        name: Human-readable endpoint name
        base_url: HTTP endpoint URL
        max_slots: Maximum concurrent requests
        context_length: Max context window in tokens
        model_id: Model alias for requests
        supports_tools: Whether endpoint supports tool calling
        supports_vision: Whether endpoint handles images
        thinking_mode: Ollama thinking effort (low/medium/high)
        idle_shutdown_seconds: Seconds of inactivity before shutdown (0=never)
        port: Server port (extracted from base_url for process management)
    """
    name: str
    base_url: str
    max_slots: int
    context_length: int
    model_id: str
    supports_tools: bool = False
    supports_vision: bool = False
    thinking_mode: Optional[str] = None
    idle_shutdown_seconds: int = 0  # 0 = never auto-shutdown
    port: int = 0  # Extracted from base_url

    # Runtime state (not serialized)
    _active_slots: int = field(default=0, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _is_running: bool = field(default=True, repr=False)  # Assume running on init

    @property
    def active_slots(self) -> int:
        """Current number of active slots."""
        return self._active_slots

    @property
    def available_slots(self) -> int:
        """Number of slots available for new requests."""
        return max(0, self.max_slots - self._active_slots)

    @property
    def is_available(self) -> bool:
        """Check if at least one slot is available."""
        return self.available_slots > 0

    async def acquire_slot(self) -> bool:
        """
        Try to acquire an inference slot.

        Returns:
            True if slot acquired, False if endpoint is at capacity.
        """
        async with self._lock:
            if self._active_slots < self.max_slots:
                self._active_slots += 1
                return True
            return False

    async def release_slot(self) -> None:
        """Release an inference slot back to the pool."""
        async with self._lock:
            self._active_slots = max(0, self._active_slots - 1)

    def status(self) -> Dict:
        """Return endpoint status for monitoring."""
        return {
            "name": self.name,
            "url": self.base_url,
            "active": self._active_slots,
            "max": self.max_slots,
            "available": self.available_slots,
        }


@dataclass
class KittyAgent:
    """
    Agent definition with model routing and soft tool guidance.

    Each agent has:
    - A primary model tier for optimal performance
    - An optional fallback tier when primary is unavailable
    - A soft tool allowlist (hints to LLM, not hard enforcement)

    Attributes:
        name: Unique agent identifier
        role: Human-readable role description
        expertise: Detailed expertise description
        system_prompt: Base system prompt for this agent
        primary_tier: Preferred model endpoint
        fallback_tier: Backup endpoint if primary is full
        tool_allowlist: Recommended tools (soft guidance)
        max_tokens: Default max tokens for responses
        temperature: Default temperature for generation
    """
    name: str
    role: str
    expertise: str
    system_prompt: str
    primary_tier: ModelTier
    fallback_tier: Optional[ModelTier] = None
    tool_allowlist: List[str] = field(default_factory=list)
    max_tokens: int = 2048
    temperature: float = 0.7

    def build_system_prompt(self, include_tools: bool = True) -> str:
        """
        Build full system prompt with optional tool guidance.

        Args:
            include_tools: Whether to append tool recommendations

        Returns:
            Complete system prompt string
        """
        prompt = self.system_prompt

        if include_tools and self.tool_allowlist:
            tools = ", ".join(self.tool_allowlist)
            prompt += f"\n\nRecommended tools for your tasks: {tools}"
            prompt += "\nUse these tools when appropriate, but you may use others if needed."

        return prompt


def _extract_port(url: str, default: int = 0) -> int:
    """Extract port number from URL."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.port or default
    except Exception:
        return default


def _load_endpoints_from_env() -> Dict[ModelTier, ModelEndpoint]:
    """
    Load endpoint configuration from environment variables.

    Matches the configuration in ops/scripts/llama/start.sh and .env.

    Idle shutdown settings:
    - 0 = never auto-shutdown (default for Ollama which has its own keep_alive)
    - >0 = shutdown after N seconds of inactivity
    """
    q4_url = os.getenv("LLAMACPP_Q4_HOST", "http://localhost:8083")
    vision_url = os.getenv("LLAMACPP_VISION_HOST", "http://localhost:8086")
    coder_url = os.getenv("LLAMACPP_CODER_HOST", "http://localhost:8087")
    summary_url = os.getenv("LLAMACPP_SUMMARY_HOST", "http://localhost:8084")
    ollama_url = os.getenv("OLLAMA_HOST", "http://localhost:11434")

    return {
        ModelTier.Q4_TOOLS: ModelEndpoint(
            name="Athene V2 Q4 (Tool Orchestrator)",
            base_url=q4_url,
            max_slots=int(os.getenv("LLAMACPP_Q4_PARALLEL", "6")),
            context_length=int(os.getenv("LLAMACPP_Q4_CTX", "131072")),
            model_id=os.getenv("LLAMACPP_Q4_ALIAS", "kitty-q4"),
            supports_tools=True,
            idle_shutdown_seconds=int(os.getenv("LLAMACPP_Q4_IDLE_SHUTDOWN_SECONDS", "900")),
            port=_extract_port(q4_url, 8083),
        ),
        ModelTier.GPTOSS_REASON: ModelEndpoint(
            name="GPT-OSS 120B (Deep Reasoner)",
            base_url=ollama_url,
            max_slots=int(os.getenv("OLLAMA_NUM_PARALLEL", "2")),
            context_length=65536,
            model_id=os.getenv("OLLAMA_MODEL", "gpt-oss-120b-judge"),
            thinking_mode=os.getenv("OLLAMA_THINK", "medium"),
            idle_shutdown_seconds=0,  # Ollama manages its own keep_alive
            port=_extract_port(ollama_url, 11434),
        ),
        ModelTier.VISION: ModelEndpoint(
            name="Gemma 3 27B Vision (Multimodal)",
            base_url=vision_url,
            max_slots=int(os.getenv("LLAMACPP_VISION_PARALLEL", "2")),
            context_length=int(os.getenv("LLAMACPP_VISION_CTX", "8192")),
            model_id=os.getenv("LLAMACPP_VISION_ALIAS", "kitty-vision"),
            supports_vision=True,
            idle_shutdown_seconds=int(os.getenv("LLAMACPP_VISION_IDLE_SHUTDOWN_SECONDS", "1800")),
            port=_extract_port(vision_url, 8086),
        ),
        ModelTier.CODER: ModelEndpoint(
            name="Qwen 32B Coder",
            base_url=coder_url,
            max_slots=int(os.getenv("LLAMACPP_CODER_PARALLEL", "4")),
            context_length=int(os.getenv("LLAMACPP_CODER_CTX", "32768")),
            model_id=os.getenv("LLAMACPP_CODER_ALIAS", "kitty-coder"),
            idle_shutdown_seconds=int(os.getenv("LLAMACPP_CODER_IDLE_SHUTDOWN_SECONDS", "900")),
            port=_extract_port(coder_url, 8087),
        ),
        ModelTier.SUMMARY: ModelEndpoint(
            name="Hermes 8B (Summarizer)",
            base_url=summary_url,
            max_slots=int(os.getenv("LLAMACPP_SUMMARY_PARALLEL", "4")),
            context_length=4096,
            model_id=os.getenv("LLAMACPP_SUMMARY_ALIAS", "kitty-summary"),
            idle_shutdown_seconds=int(os.getenv("LLAMACPP_SUMMARY_IDLE_SHUTDOWN_SECONDS", "1800")),
            port=_extract_port(summary_url, 8084),
        ),
    }


# Global endpoint registry - loaded from environment
ENDPOINTS: Dict[ModelTier, ModelEndpoint] = _load_endpoints_from_env()


def _create_agent_registry() -> Dict[str, KittyAgent]:
    """
    Create the full KITTY agent registry.

    8 specialized agents covering:
    - Research & information gathering
    - Deep reasoning & synthesis
    - CAD design & generation
    - Fabrication & 3D printing
    - Code generation
    - Vision & image analysis
    - Data analysis & metrics
    - Summarization & compression
    """
    return {
        # Research & Information Gathering
        "researcher": KittyAgent(
            name="researcher",
            role="Research Specialist",
            expertise="Web search, document analysis, citation tracking, fact verification",
            system_prompt="""You are KITTY's research agent. Your mission:
1. Search thoroughly using available tools
2. Verify claims across multiple sources
3. Track and cite all sources properly
4. Identify knowledge gaps and search to fill them
Never fabricate information. If uncertain, search again.""",
            primary_tier=ModelTier.Q4_TOOLS,
            tool_allowlist=["web_search", "fetch_webpage", "vision.image_search"],
            temperature=0.3,
        ),

        # Deep Reasoning & Synthesis
        "reasoner": KittyAgent(
            name="reasoner",
            role="Deep Reasoning Specialist",
            expertise="Complex analysis, multi-step logic, synthesis, critical evaluation",
            system_prompt="""You are KITTY's reasoning agent using GPT-OSS 120B with thinking mode.
Take your time. Think step-by-step. Consider multiple perspectives.
Your role is to synthesize information from other agents into coherent insights.
Challenge assumptions. Identify logical gaps. Provide nuanced conclusions.""",
            primary_tier=ModelTier.GPTOSS_REASON,
            fallback_tier=ModelTier.Q4_TOOLS,
            tool_allowlist=[],  # Pure reasoning, no tools
            max_tokens=4096,
            temperature=0.5,
        ),

        # CAD & Design
        "cad_designer": KittyAgent(
            name="cad_designer",
            role="CAD Generation Specialist",
            expertise="Parametric modeling, organic shapes, fabrication constraints, DFM",
            system_prompt="""You are KITTY's CAD design agent. Guidelines:
1. Always specify dimensions (prefer metric, accept imperial)
2. Consider printability: overhangs, supports, bed adhesion
3. For organic shapes, use mode='organic' (Tripo)
4. For precise geometry, use mode='parametric' (Zoo)
5. Reference images improve organic generation quality""",
            primary_tier=ModelTier.Q4_TOOLS,
            tool_allowlist=["generate_cad_model", "vision.image_search", "vision.store_selection"],
            temperature=0.4,
        ),

        # Fabrication & Printing
        "fabricator": KittyAgent(
            name="fabricator",
            role="Fabrication Engineer",
            expertise="3D printing, slicing, material selection, printer routing, G-code",
            system_prompt="""You are KITTY's fabrication agent. Responsibilities:
1. Analyze models for printability before submission
2. Select optimal printer based on: size, material, queue length
3. Configure slicer settings for material (PLA/PETG/TPU)
4. Estimate print time and material usage
5. Monitor for failures via camera integration""",
            primary_tier=ModelTier.Q4_TOOLS,
            tool_allowlist=[
                "fabrication.open_in_slicer",
                "fabrication.submit_job",
                "fabrication.check_queue",
                "fabrication.segment_mesh",
            ],
            temperature=0.2,  # Low temp for precise operations
        ),

        # Code Generation
        "coder": KittyAgent(
            name="coder",
            role="Software Engineer",
            expertise="Python, TypeScript, CadQuery, OpenSCAD, algorithm implementation",
            system_prompt="""You are KITTY's coding agent using Qwen 32B Coder.
Write clean, documented, tested code. Follow these principles:
1. Type hints in Python, TypeScript types
2. Docstrings with examples
3. Handle edge cases and errors gracefully
4. Prefer stdlib over dependencies
5. For CAD: CadQuery for parametric, OpenSCAD for CSG""",
            primary_tier=ModelTier.CODER,
            fallback_tier=ModelTier.Q4_TOOLS,
            max_tokens=4096,
            temperature=0.2,
        ),

        # Vision & Image Analysis
        "vision_analyst": KittyAgent(
            name="vision_analyst",
            role="Visual Analysis Specialist",
            expertise="Image understanding, print failure detection, CAD screenshot analysis",
            system_prompt="""You are KITTY's vision agent using Llama 3.2 Vision.
Analyze images for:
1. Print quality issues (stringing, layer adhesion, warping)
2. CAD reference matching for organic generation
3. First layer inspection for bed adhesion
4. Spaghetti/failure detection from camera feeds""",
            primary_tier=ModelTier.VISION,
            tool_allowlist=["vision.analyze_image", "camera.snapshot"],
            temperature=0.3,
        ),

        # Data Analysis & Metrics
        "analyst": KittyAgent(
            name="analyst",
            role="Data Analyst",
            expertise="Metrics interpretation, cost analysis, quality scoring, recommendations",
            system_prompt="""You are KITTY's analyst agent. Provide:
1. Clear metrics with units and context
2. Cost breakdowns (API calls, materials, time)
3. Quality scores with justification
4. Actionable recommendations
5. Trend analysis when historical data available""",
            primary_tier=ModelTier.Q4_TOOLS,
            tool_allowlist=["memory.recall", "memory.store"],
            temperature=0.3,
        ),

        # Summary & Compression
        "summarizer": KittyAgent(
            name="summarizer",
            role="Content Summarizer",
            expertise="Compression, key point extraction, TL;DR generation",
            system_prompt="""You are KITTY's summary agent using Hermes 8B.
Create concise summaries that:
1. Preserve critical information
2. Remove redundancy
3. Maintain factual accuracy
4. Fit within token budgets
5. Support voice output (conversational tone)""",
            primary_tier=ModelTier.SUMMARY,
            max_tokens=512,
            temperature=0.3,
        ),
    }


# Global agent registry
KITTY_AGENTS: Dict[str, KittyAgent] = _create_agent_registry()


def get_agent(name: str) -> Optional[KittyAgent]:
    """Get an agent by name, or None if not found."""
    return KITTY_AGENTS.get(name)


def get_endpoint(tier: ModelTier) -> Optional[ModelEndpoint]:
    """Get an endpoint by tier, or None if not found."""
    return ENDPOINTS.get(tier)


def list_agents() -> List[str]:
    """List all registered agent names."""
    return list(KITTY_AGENTS.keys())


def list_endpoints() -> Dict[str, Dict]:
    """List all endpoints with their status."""
    return {
        tier.value: endpoint.status()
        for tier, endpoint in ENDPOINTS.items()
    }
