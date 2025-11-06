# noqa: D401
"""Citation tracking for source attribution in research workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse


@dataclass
class Citation:
    """Individual citation for a source.

    Tracks metadata about sources used in research to enable
    proper attribution and verification.
    """

    url: str
    title: str
    description: str = ""
    author: str = ""
    accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_domain: str = field(default="")
    content_hash: Optional[str] = None
    relevance_score: float = 0.0

    def __post_init__(self) -> None:
        """Extract domain from URL if not provided."""
        if not self.source_domain and self.url:
            self.source_domain = self._extract_domain(self.url)

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL.

        Args:
            url: Full URL

        Returns:
            Domain name
        """
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain.startswith("www."):
                domain = domain[4:]
            return domain
        except Exception:  # noqa: BLE001
            return ""

    def to_dict(self) -> Dict:
        """Convert citation to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "url": self.url,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "accessed_at": self.accessed_at.isoformat(),
            "source_domain": self.source_domain,
            "content_hash": self.content_hash,
            "relevance_score": self.relevance_score,
        }

    def to_markdown(self, index: Optional[int] = None) -> str:
        """Format citation as markdown.

        Args:
            index: Optional citation number

        Returns:
            Markdown formatted citation
        """
        prefix = f"[{index}] " if index is not None else ""
        parts = [prefix]

        # Title and URL
        if self.title:
            parts.append(f"**{self.title}**")
        parts.append(f"- {self.url}")

        # Author if available
        if self.author:
            parts.append(f"  - Author: {self.author}")

        # Source domain
        if self.source_domain:
            parts.append(f"  - Source: {self.source_domain}")

        # Access date
        parts.append(f"  - Accessed: {self.accessed_at.strftime('%Y-%m-%d')}")

        return "\n".join(parts)

    def to_bibtex(self, cite_key: Optional[str] = None) -> str:
        """Format citation as BibTeX entry.

        Args:
            cite_key: Optional citation key (defaults to domain_year)

        Returns:
            BibTeX formatted citation
        """
        if not cite_key:
            year = self.accessed_at.year
            domain = self.source_domain.replace(".", "_")
            cite_key = f"{domain}_{year}"

        bibtex = f"@misc{{{cite_key},\n"
        bibtex += f"  title = {{{self.title}}},\n"
        if self.author:
            bibtex += f"  author = {{{self.author}}},\n"
        bibtex += f"  url = {{{self.url}}},\n"
        bibtex += f"  year = {{{self.accessed_at.year}}},\n"
        bibtex += f"  note = {{Accessed: {self.accessed_at.strftime('%Y-%m-%d')}}}\n"
        bibtex += "}"

        return bibtex


class CitationTracker:
    """Track and manage citations for research queries.

    Provides:
    - Citation collection and deduplication
    - Source ranking by relevance
    - Multiple output formats (markdown, bibtex)
    - Citation statistics
    """

    def __init__(self) -> None:
        """Initialize CitationTracker."""
        self._citations: List[Citation] = []
        self._url_to_citation: Dict[str, Citation] = {}

    def add_citation(
        self,
        url: str,
        title: str,
        description: str = "",
        author: str = "",
        content_hash: Optional[str] = None,
        relevance_score: float = 0.0,
    ) -> Citation:
        """Add a citation to the tracker.

        Args:
            url: Source URL
            title: Source title
            description: Source description/snippet
            author: Source author
            content_hash: Optional content hash for deduplication
            relevance_score: Relevance score (0.0-1.0)

        Returns:
            The added Citation object
        """
        # Check if URL already cited
        if url in self._url_to_citation:
            # Update existing citation if relevance is higher
            existing = self._url_to_citation[url]
            if relevance_score > existing.relevance_score:
                existing.relevance_score = relevance_score
                existing.description = description or existing.description
                existing.author = author or existing.author
            return existing

        # Create new citation
        citation = Citation(
            url=url,
            title=title,
            description=description,
            author=author,
            content_hash=content_hash,
            relevance_score=relevance_score,
        )

        self._citations.append(citation)
        self._url_to_citation[url] = citation

        return citation

    def get_citations(
        self,
        min_relevance: float = 0.0,
        max_citations: Optional[int] = None,
    ) -> List[Citation]:
        """Get citations, optionally filtered and sorted.

        Args:
            min_relevance: Minimum relevance score threshold
            max_citations: Maximum number of citations to return

        Returns:
            List of citations sorted by relevance (descending)
        """
        # Filter by relevance
        citations = [c for c in self._citations if c.relevance_score >= min_relevance]

        # Sort by relevance score (descending)
        citations.sort(key=lambda c: c.relevance_score, reverse=True)

        # Limit if requested
        if max_citations is not None:
            citations = citations[:max_citations]

        return citations

    def get_by_url(self, url: str) -> Optional[Citation]:
        """Get citation by URL.

        Args:
            url: Source URL

        Returns:
            Citation if found, None otherwise
        """
        return self._url_to_citation.get(url)

    def has_citation(self, url: str) -> bool:
        """Check if URL is already cited.

        Args:
            url: Source URL

        Returns:
            True if URL already cited
        """
        return url in self._url_to_citation

    def to_markdown(
        self,
        min_relevance: float = 0.0,
        max_citations: Optional[int] = None,
    ) -> str:
        """Format citations as markdown references section.

        Args:
            min_relevance: Minimum relevance score threshold
            max_citations: Maximum number of citations to return

        Returns:
            Markdown formatted citations
        """
        citations = self.get_citations(min_relevance, max_citations)

        if not citations:
            return ""

        lines = ["## References\n"]
        for i, citation in enumerate(citations, 1):
            lines.append(citation.to_markdown(index=i))
            lines.append("")  # Blank line between citations

        return "\n".join(lines)

    def to_bibtex(
        self,
        min_relevance: float = 0.0,
        max_citations: Optional[int] = None,
    ) -> str:
        """Format citations as BibTeX entries.

        Args:
            min_relevance: Minimum relevance score threshold
            max_citations: Maximum number of citations to return

        Returns:
            BibTeX formatted citations
        """
        citations = self.get_citations(min_relevance, max_citations)

        if not citations:
            return ""

        entries = []
        for i, citation in enumerate(citations, 1):
            cite_key = f"source{i}"
            entries.append(citation.to_bibtex(cite_key))

        return "\n\n".join(entries)

    def get_stats(self) -> Dict:
        """Get citation statistics.

        Returns:
            Dictionary with statistics:
                - total_citations: Total number of citations
                - unique_domains: Number of unique source domains
                - avg_relevance: Average relevance score
                - top_domains: Top 5 domains by citation count
        """
        if not self._citations:
            return {
                "total_citations": 0,
                "unique_domains": 0,
                "avg_relevance": 0.0,
                "top_domains": [],
            }

        # Count citations by domain
        domain_counts: Dict[str, int] = {}
        total_relevance = 0.0

        for citation in self._citations:
            domain = citation.source_domain
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
            total_relevance += citation.relevance_score

        # Top domains
        top_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_citations": len(self._citations),
            "unique_domains": len(domain_counts),
            "avg_relevance": total_relevance / len(self._citations),
            "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
        }

    def reset(self) -> None:
        """Clear all citations."""
        self._citations.clear()
        self._url_to_citation.clear()


__all__ = ["Citation", "CitationTracker"]
