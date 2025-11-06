# noqa: D401
"""SimHash content deduplication for filtering similar web pages."""

from __future__ import annotations

import hashlib
import re
from typing import List, Optional, Set

from simhash import Simhash


class SimHashDeduplicator:
    """Deduplicate content using SimHash algorithm.

    SimHash is a locality-sensitive hashing technique that produces similar
    hash values for similar content. It's particularly useful for detecting
    near-duplicate web pages and filtering redundant search results.

    Features:
    - Configurable similarity threshold (hamming distance)
    - Token-based fingerprinting
    - Efficient duplicate detection
    - Memory-efficient hash storage
    """

    def __init__(
        self,
        similarity_threshold: int = 3,
        min_content_length: int = 100,
    ) -> None:
        """Initialize SimHashDeduplicator.

        Args:
            similarity_threshold: Maximum hamming distance for considering content similar.
                                Lower values mean stricter matching (0-64, default 3).
                                3 = ~95% similarity, 6 = ~90% similarity, 10 = ~85% similarity
            min_content_length: Minimum content length to compute hash (chars)
        """
        self.similarity_threshold = similarity_threshold
        self.min_content_length = min_content_length
        self._seen_hashes: List[int] = []  # Store computed hashes
        self._seen_urls: Set[str] = set()  # Track URLs for exact deduplication

    def compute_hash(self, content: str) -> Optional[int]:
        """Compute SimHash for content.

        Args:
            content: Text content to hash

        Returns:
            Integer hash value, or None if content too short
        """
        if not content or len(content) < self.min_content_length:
            return None

        # Normalize and tokenize content
        normalized = self._normalize_content(content)
        tokens = self._tokenize(normalized)

        if not tokens:
            return None

        # Compute SimHash
        return Simhash(tokens).value

    def is_duplicate(
        self,
        content: str,
        url: Optional[str] = None,
    ) -> bool:
        """Check if content is a duplicate of previously seen content.

        Args:
            content: Text content to check
            url: Optional URL for exact duplicate checking

        Returns:
            True if content is similar to previously seen content
        """
        # Check exact URL match first
        if url and url in self._seen_urls:
            return True

        # Compute hash
        content_hash = self.compute_hash(content)
        if content_hash is None:
            return False  # Content too short, consider not duplicate

        # Check against all seen hashes
        for seen_hash in self._seen_hashes:
            hamming_distance = self._hamming_distance(content_hash, seen_hash)
            if hamming_distance <= self.similarity_threshold:
                return True

        return False

    def add(
        self,
        content: str,
        url: Optional[str] = None,
    ) -> bool:
        """Add content to seen set.

        Args:
            content: Text content to add
            url: Optional URL to track

        Returns:
            True if added (not a duplicate), False if duplicate
        """
        # Check if duplicate first
        if self.is_duplicate(content, url):
            return False

        # Compute and store hash
        content_hash = self.compute_hash(content)
        if content_hash is not None:
            self._seen_hashes.append(content_hash)

        # Store URL if provided
        if url:
            self._seen_urls.add(url)

        return True

    def reset(self) -> None:
        """Clear all stored hashes and URLs."""
        self._seen_hashes.clear()
        self._seen_urls.clear()

    def _normalize_content(self, content: str) -> str:
        """Normalize content for hashing.

        - Convert to lowercase
        - Remove excessive whitespace
        - Remove special characters
        - Preserve word boundaries

        Args:
            content: Raw content

        Returns:
            Normalized content
        """
        # Convert to lowercase
        normalized = content.lower()

        # Remove URLs
        normalized = re.sub(r"https?://\S+", "", normalized)

        # Remove email addresses
        normalized = re.sub(r"\S+@\S+", "", normalized)

        # Remove special characters but preserve spaces
        normalized = re.sub(r"[^a-z0-9\s]", " ", normalized)

        # Collapse multiple spaces
        normalized = re.sub(r"\s+", " ", normalized)

        return normalized.strip()

    def _tokenize(self, content: str) -> List[str]:
        """Tokenize content into words.

        Args:
            content: Normalized content

        Returns:
            List of word tokens
        """
        # Split on whitespace
        tokens = content.split()

        # Filter short tokens (likely noise)
        tokens = [t for t in tokens if len(t) >= 3]

        return tokens

    def _hamming_distance(self, hash1: int, hash2: int) -> int:
        """Calculate hamming distance between two hashes.

        Hamming distance is the number of differing bits.

        Args:
            hash1: First hash value
            hash2: Second hash value

        Returns:
            Number of differing bits
        """
        xor = hash1 ^ hash2
        return bin(xor).count("1")

    def get_stats(self) -> dict:
        """Get deduplicator statistics.

        Returns:
            Dictionary with stats:
                - total_hashes: Number of unique content hashes stored
                - total_urls: Number of unique URLs tracked
                - similarity_threshold: Current threshold setting
        """
        return {
            "total_hashes": len(self._seen_hashes),
            "total_urls": len(self._seen_urls),
            "similarity_threshold": self.similarity_threshold,
            "min_content_length": self.min_content_length,
        }


class ContentFingerprinter:
    """Alternative simpler fingerprinting using MD5 for exact duplicates.

    Use this for exact duplicate detection when SimHash is too aggressive.
    """

    def __init__(self) -> None:
        """Initialize ContentFingerprinter."""
        self._seen_fingerprints: Set[str] = set()

    def fingerprint(self, content: str) -> str:
        """Compute MD5 fingerprint of content.

        Args:
            content: Text content

        Returns:
            Hex digest of MD5 hash
        """
        normalized = content.strip().lower()
        return hashlib.md5(normalized.encode("utf-8")).hexdigest()

    def is_duplicate(self, content: str) -> bool:
        """Check if content fingerprint has been seen.

        Args:
            content: Text content

        Returns:
            True if exact duplicate
        """
        fp = self.fingerprint(content)
        return fp in self._seen_fingerprints

    def add(self, content: str) -> bool:
        """Add content fingerprint.

        Args:
            content: Text content

        Returns:
            True if added (not duplicate), False if duplicate
        """
        fp = self.fingerprint(content)
        if fp in self._seen_fingerprints:
            return False
        self._seen_fingerprints.add(fp)
        return True

    def reset(self) -> None:
        """Clear all fingerprints."""
        self._seen_fingerprints.clear()


__all__ = ["SimHashDeduplicator", "ContentFingerprinter"]
