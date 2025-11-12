#!/usr/bin/env python3
"""
Generate knowledge base content using KITTY's autonomous research capabilities.
This script demonstrates the full autonomous workflow: research → format → save → commit.
"""
import asyncio
import json
import re
import sys
from pathlib import Path

# Add services to path so we can import brain modules
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services/brain/src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services/common/src"))

import httpx
from brain.knowledge.updater import KnowledgeUpdater

# Knowledge base entries to generate
MATERIALS = [
    {"slug": "pla", "name": "PLA (Polylactic Acid)"},
    {"slug": "petg", "name": "PETG"},
    {"slug": "abs", "name": "ABS"},
]

TECHNIQUES = [
    {"slug": "first-layer-adhesion", "name": "First Layer Adhesion"},
    {"slug": "stringing-prevention", "name": "Stringing Prevention"},
]


async def query_brain(prompt: str, verbosity: int = 5) -> dict:
    """Query KITTY brain with research prompt."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        try:
            response = await client.post(
                "http://localhost:8000/api/query",
                json={
                    "intent": "query.text",
                    "prompt": prompt,
                    "conversationId": "kb-generation",
                    "userId": "autonomous",
                    "verbosity": verbosity,
                    "useAgent": False,  # Disable ReAct agent to avoid 400 errors
                    "freshnessRequired": True,  # Force MCP tier for web research
                    "forceTier": "mcp",  # Explicitly request MCP (Perplexity) tier
                },
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"❌ Error querying brain: {e}")
            return {"error": str(e)}


def parse_material_response(response_text: str) -> dict:
    """Parse material research response into structured metadata + content.

    Args:
        response_text: Response from brain

    Returns:
        Dict with 'metadata' and 'content' keys
    """
    # Try to extract JSON block if present
    json_match = re.search(r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            # Extract metadata fields
            metadata = {
                "cost_per_kg": data.get("cost_per_kg", "Unknown"),
                "density": data.get("density", "Unknown"),
                "print_temp": data.get("print_temp", "Unknown"),
                "bed_temp": data.get("bed_temp", "Unknown"),
                "sustainability_score": data.get("sustainability_score", 5),
                "suppliers": data.get("suppliers", []),
            }
            # Use remaining response as content
            content = response_text.replace(json_match.group(0), "").strip()
            return {"metadata": metadata, "content": content}
        except json.JSONDecodeError:
            pass

    # Fallback: use entire response as content with empty metadata
    return {
        "metadata": {
            "cost_per_kg": "See content",
            "density": "See content",
            "print_temp": "See content",
            "bed_temp": "See content",
            "sustainability_score": 5,
            "suppliers": [],
        },
        "content": response_text,
    }


async def generate_material(material: dict, updater: KnowledgeUpdater):
    """Generate material documentation using research tools."""
    prompt = f"""Research {material['name']} for 3D printing.

Use web_search to find current information about:
- Cost per kg (USD)
- Density (g/cm³)
- Print temperature (°C)
- Bed temperature (°C)
- Common suppliers
- Key properties and applications

Format your response as markdown with sections for Overview, Properties, Applications, Print Settings, and Tips."""

    print(f"\n🔍 Researching {material['name']}...")
    result = await query_brain(prompt, verbosity=5)

    if "error" in result:
        print(f"❌ Failed: {result['error']}")
        return None

    # Extract the actual response from the nested result structure
    response_text = result.get("result", {}).get("output", "")
    print(f"✅ Received {len(response_text)} characters")

    # Check if research tools were used
    routing_info = result.get("routing", {})
    tool_calls = routing_info.get("metadata", {}).get("tool_calls", [])
    if tool_calls:
        print(f"   🔧 Used {len(tool_calls)} tool(s):")
        for tc in tool_calls:
            print(f"      - {tc.get('name', 'unknown')}")
    else:
        print("   ⚠️  No tools used - may be from training data")

    # Parse response
    parsed = parse_material_response(response_text)

    # Save using KnowledgeUpdater
    try:
        file_path = updater.create_material(
            slug=material["slug"],
            name=material["name"],
            content=parsed["content"],
            metadata=parsed["metadata"],
            auto_commit=False,  # We'll commit in batch
        )
        print(f"   💾 Saved to {file_path.name}")
        return file_path
    except Exception as e:
        print(f"   ❌ Failed to save: {e}")
        return None


async def generate_technique(technique: dict, updater: KnowledgeUpdater):
    """Generate technique guide using research tools."""
    prompt = f"""Research troubleshooting guide for {technique['name']} in 3D printing.

Use web_search to find current best practices and format response as markdown with:
- Problem description
- Common causes
- Solutions (numbered list)
- Prevention tips
- Recommended slicer settings"""

    print(f"\n🔍 Researching {technique['name']}...")
    result = await query_brain(prompt, verbosity=5)

    if "error" in result:
        print(f"❌ Failed: {result['error']}")
        return None

    # Extract the actual response from the nested result structure
    response_text = result.get("result", {}).get("output", "")
    print(f"✅ Received {len(response_text)} characters")

    # Check tool usage
    routing_info = result.get("routing", {})
    tool_calls = routing_info.get("metadata", {}).get("tool_calls", [])
    if tool_calls:
        print(f"   🔧 Used {len(tool_calls)} tool(s)")

    # Save using KnowledgeUpdater
    try:
        file_path = updater.create_technique(
            slug=technique["slug"],
            name=technique["name"],
            content=response_text,
            auto_commit=False,
        )
        print(f"   💾 Saved to {file_path.name}")
        return file_path
    except Exception as e:
        print(f"   ❌ Failed to save: {e}")
        return None


async def main():
    print("🤖 KITTY Autonomous Knowledge Base Generator")
    print("=" * 60)
    print("Demonstrating autonomous research workflow:\n")
    print("  1. Query brain with research prompts")
    print("  2. Brain uses web_search tool")
    print("  3. Parse and structure results")
    print("  4. Save with proper YAML frontmatter")
    print("  5. Git commit (optional)\n")

    # Initialize updater
    updater = KnowledgeUpdater()
    print(f"📂 Knowledge base: {updater.kb_path}\n")

    # Generate materials
    print("\n📦 Generating Materials")
    print("-" * 60)
    for material in MATERIALS:
        await generate_material(material, updater)
        await asyncio.sleep(2)  # Rate limit

    # Generate techniques
    print("\n\n🛠️  Generating Techniques")
    print("-" * 60)
    for technique in TECHNIQUES:
        await generate_technique(technique, updater)
        await asyncio.sleep(2)  # Rate limit

    print("\n\n✅ Knowledge base generation complete!")
    print(f"\nGenerated files:")
    print(f"  Materials: {', '.join(updater.list_materials())}")
    print(f"  Techniques: {', '.join(updater.list_techniques())}")

    print("\n💡 To commit these files, run:")
    print("   git add knowledge/")
    print('   git commit -m "KB: Autonomous content generation"')

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
