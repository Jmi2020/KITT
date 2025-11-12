#!/usr/bin/env python3
"""Retag development memories with meta/dev/collective tags.

This script scans existing memories in Qdrant and adds appropriate tags
to development-related memories so they can be filtered out for proposers
while remaining available for judges.

Usage:
    python scripts/retag_dev_memories.py
    python scripts/retag_dev_memories.py --dry-run  # preview changes
    python scripts/retag_dev_memories.py --limit 1000  # process max 1000 memories
"""

import argparse
import os
import re
from typing import List, Set

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct


# Configuration from environment
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "kitty_memory")

# Patterns to identify meta/dev memories
PATTERNS = [
    r"(?i)KITTY (is|was|will be|can|should|development|integration)",
    r"(?i)multi[- ]agent",
    r"(?i)collective",
    r"(?i)development (notes?|journey|milestone)",
    r"(?i)llama\.?cpp",
    r"(?i)(brain|gateway|cad|fabrication) (service|container)",
    r"(?i)(async|sync) (execution|performance|optimization)",
    r"(?i)(LangGraph|StateGraph|graph compilation)",
    r"(?i)(Q4|F16) (model|server)",
    r"(?i)proposer[- ]blinding",
    r"(?i)tag[- ]aware",
    r"(?i)(Prometheus|metrics|histogram|counter)",
]


def is_meta_content(text: str) -> bool:
    """Check if content matches meta/dev patterns."""
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in PATTERNS)


def retag_memories(dry_run: bool = False, limit: int = 5000) -> None:
    """Retag memories that match meta/dev patterns.

    Args:
        dry_run: If True, only print what would be changed
        limit: Maximum number of memories to process
    """
    client = QdrantClient(url=QDRANT_URL)

    print(f"Connecting to Qdrant at {QDRANT_URL}")
    print(f"Collection: {COLLECTION_NAME}")
    print(f"Dry run: {dry_run}")
    print()

    # Check if collection exists
    collections = client.get_collections()
    collection_names = [c.name for c in collections.collections]

    if COLLECTION_NAME not in collection_names:
        print(f"Collection '{COLLECTION_NAME}' not found!")
        return

    # Scroll through all memories
    scroll_filter = None
    processed = 0
    tagged_count = 0
    to_upsert: List[PointStruct] = []

    print("Scanning memories...")
    offset = None

    while processed < limit:
        # Fetch batch of memories
        records, offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=min(100, limit - processed),
            offset=offset,
            with_payload=True,
            with_vectors=False  # Don't need vectors for retagging
        )

        if not records:
            break

        for point in records:
            processed += 1
            payload = point.payload or {}
            content = payload.get("content", "")
            existing_tags = set(payload.get("tags", []))

            # Check if this is a meta/dev memory
            if is_meta_content(content):
                # Add meta/dev/collective tags
                new_tags = existing_tags | {"meta", "dev", "collective"}

                if new_tags != existing_tags:
                    tagged_count += 1

                    preview = content[:80] + "..." if len(content) > 80 else content
                    print(f"\n[{tagged_count}] ID: {point.id}")
                    print(f"Content: {preview}")
                    print(f"Old tags: {sorted(existing_tags) if existing_tags else '(none)'}")
                    print(f"New tags: {sorted(new_tags)}")

                    if not dry_run:
                        # Prepare update (keep vector as None for metadata-only update)
                        to_upsert.append(
                            PointStruct(
                                id=point.id,
                                vector={},  # Empty vector for update
                                payload={**payload, "tags": list(new_tags)}
                            )
                        )

        # Batch upsert every 50 records
        if not dry_run and len(to_upsert) >= 50:
            client.update_collection(
                collection_name=COLLECTION_NAME,
                points=to_upsert
            )
            print(f"\n✓ Updated batch of {len(to_upsert)} memories")
            to_upsert = []

    # Final batch
    if not dry_run and to_upsert:
        client.update_collection(
            collection_name=COLLECTION_NAME,
            points=to_upsert
        )
        print(f"\n✓ Updated final batch of {len(to_upsert)} memories")

    # Summary
    print("\n" + "=" * 60)
    print(f"Processed: {processed} memories")
    print(f"Tagged: {tagged_count} memories with meta/dev/collective")
    if dry_run:
        print("\n(Dry run - no changes made)")
    else:
        print("\n✓ Retagging complete!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Retag development memories for collective-confidentiality"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying memories"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5000,
        help="Maximum number of memories to process"
    )

    args = parser.parse_args()

    try:
        retag_memories(dry_run=args.dry_run, limit=args.limit)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    except Exception as e:
        print(f"\n\nError: {e}")
        raise


if __name__ == "__main__":
    main()
