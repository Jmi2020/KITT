# noqa: D401
"""Model card data from HuggingFace and official sources.

This module contains detailed model card information for all models
available in KITTY, sourced from HuggingFace and official documentation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ModelCard:
    """Detailed model card information."""

    id: str
    name: str
    short_description: str
    description: str
    capabilities: List[str]
    parameters: str
    context_length: str
    architecture: str
    developer: str
    license: str
    huggingface_url: Optional[str] = None
    docs_url: Optional[str] = None
    release_date: Optional[str] = None
    base_model: Optional[str] = None
    quantization: Optional[str] = None
    supports_vision: bool = False
    supports_tools: bool = False
    languages: Optional[List[str]] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for API response."""
        return {
            "id": self.id,
            "name": self.name,
            "short_description": self.short_description,
            "description": self.description,
            "capabilities": self.capabilities,
            "parameters": self.parameters,
            "context_length": self.context_length,
            "architecture": self.architecture,
            "developer": self.developer,
            "license": self.license,
            "huggingface_url": self.huggingface_url,
            "docs_url": self.docs_url,
            "release_date": self.release_date,
            "base_model": self.base_model,
            "quantization": self.quantization,
            "supports_vision": self.supports_vision,
            "supports_tools": self.supports_tools,
            "languages": self.languages,
        }


# =============================================================================
# LOCAL MODELS
# =============================================================================

LLAMA_3_3_70B = ModelCard(
    id="gpt-oss",
    name="Llama 3.3 70B Instruct",
    short_description="Primary reasoner with thinking mode",
    description=(
        "Meta's Llama 3.3 is an instruction-tuned generative model with 70 billion "
        "parameters designed for multilingual dialogue applications. Released December 2024, "
        "it outperforms many open-source and proprietary chat models on industry benchmarks."
    ),
    capabilities=[
        "Multilingual support (8 languages)",
        "Tool use and function calling",
        "Strong code generation (88.4% HumanEval)",
        "Enhanced mathematical reasoning (77.0 MATH)",
        "Long context handling (128K tokens)",
        "86.0 MMLU score",
    ],
    parameters="70B",
    context_length="128,000 tokens",
    architecture="Optimized Transformer with Grouped-Query Attention (GQA)",
    developer="Meta AI",
    license="Llama 3.3 Community License",
    huggingface_url="https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct",
    docs_url="https://llama.meta.com/",
    release_date="December 2024",
    quantization="F16 (full precision)",
    supports_tools=True,
    languages=["English", "German", "French", "Italian", "Portuguese", "Hindi", "Spanish", "Thai"],
)

ATHENE_V2_AGENT = ModelCard(
    id="athene-q4",
    name="Athene V2 Agent",
    short_description="Fast tool orchestrator",
    description=(
        "An open-source agent LLM developed by Nexusflow, fine-tuned from Qwen2.5-72B-Instruct "
        "for tool use and agentic applications. Surpasses GPT-4o by 18% in function calling "
        "success rates and 17% in agentic success rates."
    ),
    capabilities=[
        "Superior function calling (18% better than GPT-4o)",
        "Complex reasoning chains",
        "Multiple sequential tool calls",
        "Generalizes to unseen functions",
        "OpenAI-compatible interface",
        "Handles nested dependencies",
    ],
    parameters="73B",
    context_length="32,000 tokens",
    architecture="Qwen2.5-based Transformer",
    developer="Nexusflow",
    license="Nexusflow Research License",
    huggingface_url="https://huggingface.co/Nexusflow/Athene-V2-Agent",
    docs_url="https://github.com/nexusflowai/NexusBench",
    release_date="November 2024",
    base_model="Qwen/Qwen2.5-72B-Instruct",
    quantization="Q4_K_M",
    supports_tools=True,
)

GEMMA_3_27B = ModelCard(
    id="gemma-vision",
    name="Gemma 3 27B Vision",
    short_description="Multimodal image understanding",
    description=(
        "Gemma 3 is a lightweight, multimodal open model from Google built on Gemini technology. "
        "The 27B instruction-tuned variant processes text and image input for multimodal tasks "
        "with support for over 140 languages."
    ),
    capabilities=[
        "Image understanding and analysis",
        "Visual question answering",
        "Document understanding (DocVQA: 85.6%)",
        "Text extraction from images",
        "140+ language support",
        "Strong reasoning (MMLU: 78.6%)",
    ],
    parameters="27B",
    context_length="128,000 tokens",
    architecture="Transformer with multimodal encoder",
    developer="Google DeepMind",
    license="Gemma License",
    huggingface_url="https://huggingface.co/google/gemma-3-27b-it",
    docs_url="https://ai.google.dev/gemma",
    release_date="2024",
    quantization="Q4_K_M",
    supports_vision=True,
    languages=["140+ languages"],
)

HERMES_3_8B = ModelCard(
    id="hermes-summary",
    name="Hermes 3 8B",
    short_description="Response summarization",
    description=(
        "Hermes 3 is Nous Research's flagship language model built on Llama-3.1-8B, "
        "designed as a generalist assistant with advanced agentic capabilities, "
        "function calling, and structured output generation."
    ),
    capabilities=[
        "Function calling with structured output",
        "JSON mode for schema-compliant responses",
        "Multi-turn conversation coherence",
        "Roleplaying and reasoning",
        "Code generation",
        "ChatML prompt format compatible",
    ],
    parameters="8B",
    context_length="128,000 tokens",
    architecture="Llama 3.1 Transformer",
    developer="Nous Research",
    license="Llama 3.1 Community License",
    huggingface_url="https://huggingface.co/NousResearch/Hermes-3-Llama-3.1-8B",
    docs_url="https://nousresearch.com/",
    release_date="2024",
    base_model="meta-llama/Llama-3.1-8B",
    quantization="Q4_K_M",
    supports_tools=True,
)

QWEN_CODER_32B = ModelCard(
    id="kitty-coder",
    name="Qwen2.5-Coder 32B",
    short_description="Code generation specialist",
    description=(
        "Qwen2.5-Coder-32B-Instruct is a code-focused large language model developed by "
        "Alibaba Cloud's Qwen team. Trained on 5.5 trillion tokens including source code "
        "and synthetic data, it achieves coding abilities matching GPT-4o."
    ),
    capabilities=[
        "Expert code generation",
        "Code fixing and debugging",
        "128K context with YaRN",
        "Strong mathematics support",
        "Code agent capabilities",
        "Multi-language programming",
    ],
    parameters="32.5B",
    context_length="128,000 tokens",
    architecture="Transformer with RoPE, SwiGLU, RMSNorm, GQA",
    developer="Alibaba Cloud (Qwen Team)",
    license="Qwen License",
    huggingface_url="https://huggingface.co/Qwen/Qwen2.5-Coder-32B-Instruct",
    docs_url="https://qwenlm.github.io/",
    release_date="2024",
    quantization="Q8_0",
    supports_tools=True,
)


# =============================================================================
# CLOUD MODELS
# =============================================================================

GPT_5 = ModelCard(
    id="gpt5",
    name="GPT-5.1",
    short_description="OpenAI's latest model",
    description=(
        "OpenAI's most advanced language model with enhanced reasoning, coding, "
        "and multimodal capabilities. Offers state-of-the-art performance across "
        "a wide range of tasks."
    ),
    capabilities=[
        "Advanced reasoning and problem solving",
        "Code generation and analysis",
        "Long context support",
        "Function calling",
        "Multimodal input",
        "Safety alignment",
    ],
    parameters="Undisclosed",
    context_length="128,000+ tokens",
    architecture="Transformer (proprietary)",
    developer="OpenAI",
    license="Commercial API",
    docs_url="https://platform.openai.com/docs",
)

CLAUDE_4 = ModelCard(
    id="claude",
    name="Claude 4.5",
    short_description="Anthropic's latest model",
    description=(
        "Anthropic's most capable AI assistant with strong reasoning, analysis, "
        "and creative writing abilities. Known for helpful, harmless, and honest responses."
    ),
    capabilities=[
        "Extended thinking mode",
        "Long context (200K tokens)",
        "Advanced code generation",
        "Document analysis",
        "Function calling",
        "Constitutional AI safety",
    ],
    parameters="Undisclosed",
    context_length="200,000 tokens",
    architecture="Transformer (proprietary)",
    developer="Anthropic",
    license="Commercial API",
    docs_url="https://docs.anthropic.com/",
)

PERPLEXITY = ModelCard(
    id="perplexity",
    name="Perplexity Sonar",
    short_description="Web-connected AI search",
    description=(
        "Perplexity's AI-powered search model with real-time web access. "
        "Provides accurate, cited responses by searching the internet and "
        "synthesizing information from multiple sources."
    ),
    capabilities=[
        "Real-time web search",
        "Source citations",
        "Up-to-date information",
        "Research synthesis",
        "Factual accuracy focus",
        "Multi-source verification",
    ],
    parameters="Undisclosed",
    context_length="128,000 tokens",
    architecture="Transformer with search integration",
    developer="Perplexity AI",
    license="Commercial API",
    docs_url="https://docs.perplexity.ai/",
)

GEMINI = ModelCard(
    id="gemini",
    name="Gemini Pro",
    short_description="Google's multimodal model",
    description=(
        "Google's most capable multimodal AI model, built on decades of AI research. "
        "Excels at reasoning, coding, and understanding across text, images, and audio."
    ),
    capabilities=[
        "Multimodal understanding",
        "Long context (2M tokens)",
        "Advanced reasoning",
        "Code generation",
        "Function calling",
        "Grounding with Google Search",
    ],
    parameters="Undisclosed",
    context_length="2,000,000 tokens",
    architecture="Transformer (proprietary)",
    developer="Google DeepMind",
    license="Commercial API",
    docs_url="https://ai.google.dev/docs",
    supports_vision=True,
)


# =============================================================================
# MODEL REGISTRY
# =============================================================================

MODEL_CARDS: Dict[str, ModelCard] = {
    # Local models
    "gpt-oss": LLAMA_3_3_70B,
    "athene-q4": ATHENE_V2_AGENT,
    "gemma-vision": GEMMA_3_27B,
    "hermes-summary": HERMES_3_8B,
    "kitty-coder": QWEN_CODER_32B,
    # Cloud models
    "gpt5": GPT_5,
    "claude": CLAUDE_4,
    "perplexity": PERPLEXITY,
    "gemini": GEMINI,
}


def get_model_card(model_id: str) -> Optional[ModelCard]:
    """Get model card by ID.

    Args:
        model_id: Model identifier (e.g., "gpt-oss", "athene-q4")

    Returns:
        ModelCard if found, None otherwise
    """
    return MODEL_CARDS.get(model_id)


def get_all_model_cards() -> Dict[str, ModelCard]:
    """Get all model cards.

    Returns:
        Dictionary of model_id -> ModelCard
    """
    return MODEL_CARDS


__all__ = [
    "ModelCard",
    "MODEL_CARDS",
    "get_model_card",
    "get_all_model_cards",
]
