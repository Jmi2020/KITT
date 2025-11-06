#!/usr/bin/env python3
"""Test script for conversing with KITTY about CAD modeling."""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

import httpx

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent / "services" / "brain" / "src"))

from brain.prompts.expert_system import (
    get_chain_of_thought_prompt,
    get_expert_system_prompt,
)


LLAMACPP_URL = "http://localhost:8082/completion"
LOG_FILE = Path(__file__).parent.parent / "logs" / "kitty_cad_conversation.jsonl"


async def query_kitty(prompt: str, model_alias: str = "kitty-coder") -> dict:
    """Query KITTY via llama.cpp server.

    Args:
        prompt: The formatted prompt to send
        model_alias: Model alias to use

    Returns:
        Response dict with content and metadata
    """
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            LLAMACPP_URL,
            json={
                "prompt": prompt,
                "n_predict": 512,
                "temperature": 0.7,
                "top_p": 0.95,
                "repeat_penalty": 1.1,
                "stop": ["User:", "Assistant:", "<|im_end|>", "<|endoftext|>"],
            },
        )
        response.raise_for_status()
        return response.json()


def log_conversation(
    query: str,
    prompt: str,
    response: dict,
    mode: str,
    verbosity: int,
):
    """Log conversation turn to JSONL file."""
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "query": query,
        "mode": mode,
        "verbosity": verbosity,
        "prompt": prompt,
        "response": response.get("content", ""),
        "tokens_predicted": response.get("tokens_predicted", 0),
        "timings": response.get("timings", {}),
    }

    with LOG_FILE.open("a") as f:
        f.write(json.dumps(log_entry) + "\n")

    return log_entry


async def main():
    """Run a conversation with KITTY about CAD modeling."""
    print("🤖 KITTY CAD Conversation Test\n")
    print(f"📝 Logging to: {LOG_FILE}\n")

    # Test 1: Chain-of-thought reasoning
    print("=" * 80)
    print("TEST 1: Chain-of-Thought Reasoning")
    print("=" * 80)

    query1 = "What are the pros and cons of coding CAD shapes in Python with CadQuery versus using a GUI like FreeCAD for 3D printing?"

    print(f"\n👤 Query: {query1}\n")

    prompt1 = get_chain_of_thought_prompt(query1)
    print("🧠 Using chain-of-thought prompt...\n")

    response1 = await query_kitty(prompt1)
    answer1 = response1.get("content", "")

    print(f"🤖 KITTY Response:\n{answer1}\n")

    log_entry1 = log_conversation(query1, prompt1, response1, "chain_of_thought", 3)
    print(
        f"⏱️  Generation time: {log_entry1['timings'].get('predicted_ms', 0) / 1000:.2f}s"
    )
    print(f"📊 Tokens: {log_entry1['tokens_predicted']}\n")

    # Test 2: Expert system with spoken output
    print("=" * 80)
    print("TEST 2: Expert System (Spoken Mode)")
    print("=" * 80)

    query2 = "I want to print a custom mounting bracket for my workshop. Should I code it or use CAD software?"

    print(f"\n👤 Query: {query2}\n")

    prompt2 = get_expert_system_prompt(query2, verbosity=3, mode="spoken")
    print("🗣️  Using expert system prompt (spoken mode)...\n")

    response2 = await query_kitty(prompt2)
    answer2 = response2.get("content", "")

    print(f"🤖 KITTY Response (TTS-ready):\n{answer2}\n")

    log_entry2 = log_conversation(query2, prompt2, response2, "expert_spoken", 3)
    print(
        f"⏱️  Generation time: {log_entry2['timings'].get('predicted_ms', 0) / 1000:.2f}s"
    )
    print(f"📊 Tokens: {log_entry2['tokens_predicted']}\n")

    # Test 3: Terse response
    print("=" * 80)
    print("TEST 3: Terse Expert Response (V=1)")
    print("=" * 80)

    query3 = "Best tool for parametric sheet metal designs?"

    print(f"\n👤 Query: {query3}\n")

    prompt3 = get_expert_system_prompt(query3, verbosity=1, mode="spoken")
    print("⚡ Using expert system prompt (V=1 - terse)...\n")

    response3 = await query_kitty(prompt3)
    answer3 = response3.get("content", "")

    print(f"🤖 KITTY Response:\n{answer3}\n")

    log_entry3 = log_conversation(query3, prompt3, response3, "expert_terse", 1)
    print(
        f"⏱️  Generation time: {log_entry3['timings'].get('predicted_ms', 0) / 1000:.2f}s"
    )
    print(f"📊 Tokens: {log_entry3['tokens_predicted']}\n")

    print("=" * 80)
    print(f"✅ Conversation logged to: {LOG_FILE}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
