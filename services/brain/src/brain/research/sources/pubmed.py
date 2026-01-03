"""
PubMed Central API client for paper harvesting.

PubMed provides access to biomedical and life sciences literature.
The E-utilities API is free with an API key for higher rate limits.

Rate Limit: 3 requests/second without key, 10/second with key
API Docs: https://www.ncbi.nlm.nih.gov/books/NBK25501/
"""

import asyncio
import xml.etree.ElementTree as ET
from typing import AsyncIterator, Optional, List, Dict, Any
from datetime import datetime
from urllib.parse import urlencode
import logging
import os
import re

from .base import (
    AcademicSource,
    PaperMetadata,
    RateLimitConfig,
    SourcePriority,
)

logger = logging.getLogger(__name__)

PUBMED_EUTILS_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_PMC_URL = "https://www.ncbi.nlm.nih.gov/pmc/articles"


class PubMedSource(AcademicSource):
    """
    PubMed Central API client via NCBI E-utilities.

    Features:
    - Access to biomedical literature
    - Free API with optional key for higher limits
    - Rate limit: 3 req/sec without key, 10/sec with key
    - Full text available for PMC articles

    Example usage:
        source = PubMedSource(api_key=os.getenv("NCBI_API_KEY"))
        async for paper in source.search("CRISPR gene editing", max_results=50):
            print(f"{paper.title} - PMID: {paper.pubmed_id}")
    """

    def __init__(self, api_key: Optional[str] = None):
        # Rate limit depends on whether API key is provided
        # Without key: 3/sec, With key: 10/sec
        rate = 10.0 if api_key else 3.0
        burst = 10 if api_key else 3

        super().__init__(
            rate_limit=RateLimitConfig(
                requests_per_second=rate,
                burst_limit=burst,
                retry_after_seconds=30.0,
            ),
            api_key=api_key or os.getenv("NCBI_API_KEY"),
            base_url=PUBMED_EUTILS_URL,
        )

    @property
    def name(self) -> str:
        return "PubMed"

    @property
    def priority(self) -> SourcePriority:
        return SourcePriority.PUBMED

    def _get_default_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": "KITT-Research-Harvester/1.0 (Academic Research; mailto:research@kitty.local)",
            "Accept": "application/xml",
        }

    def _build_api_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Add API key to params if available."""
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    async def search(
        self,
        query: str,
        max_results: int = 100,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        categories: Optional[List[str]] = None,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Search PubMed for papers using E-utilities.

        Uses a two-step process:
        1. esearch to get PMIDs matching query
        2. efetch to get full metadata for each PMID

        Args:
            query: Search query string
            max_results: Maximum results to return
            date_from: Filter by publication date (start)
            date_to: Filter by publication date (end)
            categories: MeSH terms to filter by (optional)

        Yields:
            PaperMetadata for each matching paper
        """
        # Build search query with date filters
        search_query = query
        if date_from:
            search_query += f" AND {date_from.strftime('%Y/%m/%d')}[PDAT]"
        if date_to:
            search_query += f" AND {date_to.strftime('%Y/%m/%d')}[PDAT]"
        if categories:
            mesh_query = " OR ".join(f'"{cat}"[MeSH]' for cat in categories)
            search_query = f"({search_query}) AND ({mesh_query})"

        # Step 1: Get PMIDs via esearch
        pmids = await self._esearch(search_query, max_results)
        if not pmids:
            logger.debug(f"PubMed search returned no results for: {query[:50]}...")
            return

        # Step 2: Fetch metadata in batches
        batch_size = 100
        yielded = 0

        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            papers = await self._efetch(batch)

            for paper in papers:
                yield paper
                yielded += 1

                if yielded >= max_results:
                    break

            if yielded >= max_results:
                break

        logger.info(f"PubMed search yielded {yielded} papers for query: {query[:50]}...")

    async def _esearch(
        self,
        query: str,
        max_results: int,
    ) -> List[str]:
        """Execute esearch to get PMIDs."""
        await self._acquire_rate_limit()

        params = self._build_api_params({
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "xml",
            "usehistory": "n",
        })

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/esearch.fcgi",
                params=params,
            )
            response.raise_for_status()

            root = ET.fromstring(response.text)
            pmids = [id_elem.text for id_elem in root.findall(".//Id") if id_elem.text]

            logger.debug(f"PubMed esearch found {len(pmids)} PMIDs")
            return pmids

        except Exception as e:
            logger.error(f"PubMed esearch error: {e}")
            return []

    async def _efetch(self, pmids: List[str]) -> List[PaperMetadata]:
        """Fetch full metadata for list of PMIDs."""
        if not pmids:
            return []

        await self._acquire_rate_limit()

        params = self._build_api_params({
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        })

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/efetch.fcgi",
                params=params,
            )
            response.raise_for_status()

            papers = []
            root = ET.fromstring(response.text)

            for article in root.findall(".//PubmedArticle"):
                paper = self._parse_article(article)
                if paper:
                    papers.append(paper)

            return papers

        except ET.ParseError as e:
            logger.error(f"PubMed XML parse error: {e}")
            return []
        except Exception as e:
            logger.error(f"PubMed efetch error: {e}")
            return []

    def _parse_article(self, article: ET.Element) -> Optional[PaperMetadata]:
        """Parse PubMed XML article into PaperMetadata."""
        try:
            medline = article.find(".//MedlineCitation")
            if medline is None:
                return None

            pmid_elem = medline.find(".//PMID")
            pmid = pmid_elem.text if pmid_elem is not None else ""
            if not pmid:
                return None

            # Title
            title_elem = medline.find(".//ArticleTitle")
            title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

            # Abstract
            abstract_parts = []
            for abstract_text in medline.findall(".//AbstractText"):
                if abstract_text.text:
                    label = abstract_text.get("Label", "")
                    if label:
                        abstract_parts.append(f"{label}: {abstract_text.text}")
                    else:
                        abstract_parts.append(abstract_text.text)
            abstract = " ".join(abstract_parts)

            # Authors
            authors = []
            for author in medline.findall(".//Author"):
                last_name = author.find("LastName")
                fore_name = author.find("ForeName")
                if last_name is not None and last_name.text:
                    name = last_name.text
                    if fore_name is not None and fore_name.text:
                        name = f"{fore_name.text} {name}"
                    authors.append(name)

            # Publication date
            pub_date = None
            date_elem = medline.find(".//PubDate")
            if date_elem is not None:
                year_elem = date_elem.find("Year")
                month_elem = date_elem.find("Month")
                day_elem = date_elem.find("Day")

                if year_elem is not None and year_elem.text:
                    year = int(year_elem.text)
                    month = 1
                    day = 1

                    if month_elem is not None and month_elem.text:
                        try:
                            month = int(month_elem.text)
                        except ValueError:
                            # Month might be abbreviated name
                            month_names = {
                                "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4,
                                "May": 5, "Jun": 6, "Jul": 7, "Aug": 8,
                                "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12
                            }
                            month = month_names.get(month_elem.text[:3], 1)

                    if day_elem is not None and day_elem.text:
                        try:
                            day = int(day_elem.text)
                        except ValueError:
                            day = 1

                    try:
                        pub_date = datetime(year, month, day)
                    except ValueError:
                        pub_date = datetime(year, 1, 1)

            # DOI
            doi = None
            article_ids = article.find(".//PubmedData/ArticleIdList")
            if article_ids is not None:
                for article_id in article_ids.findall("ArticleId"):
                    if article_id.get("IdType") == "doi":
                        doi = article_id.text
                        break

            # PMC ID (for PDF access)
            pmc_id = None
            if article_ids is not None:
                for article_id in article_ids.findall("ArticleId"):
                    if article_id.get("IdType") == "pmc":
                        pmc_id = article_id.text
                        break

            # PDF URL (only available for PMC articles)
            pdf_url = None
            if pmc_id:
                # Strip "PMC" prefix if present
                pmc_num = pmc_id.replace("PMC", "")
                pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_num}/pdf/"

            # Source URL
            source_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"

            # MeSH terms as categories
            categories = []
            for mesh in medline.findall(".//MeshHeading/DescriptorName"):
                if mesh.text:
                    categories.append(mesh.text)

            return PaperMetadata(
                source_id=f"pubmed:{pmid}",
                title=title,
                abstract=abstract,
                authors=authors,
                published_date=pub_date,
                doi=doi,
                pubmed_id=pmid,
                pdf_url=pdf_url,
                source_url=source_url,
                categories=categories[:10],  # Limit categories
                source="pubmed",
            )

        except Exception as e:
            logger.error(f"Failed to parse PubMed article: {e}")
            return None

    async def get_paper(self, paper_id: str) -> Optional[PaperMetadata]:
        """
        Get paper by PubMed ID.

        Args:
            paper_id: PMID (e.g., "12345678" or "pubmed:12345678")

        Returns:
            PaperMetadata or None if not found
        """
        # Strip prefix if present
        if paper_id.startswith("pubmed:"):
            paper_id = paper_id[7:]

        papers = await self._efetch([paper_id])
        return papers[0] if papers else None

    async def get_full_text(self, paper: PaperMetadata) -> Optional[str]:
        """
        Get full text for a PubMed paper.

        Full text is only available for PMC (PubMed Central) articles.
        For other articles, this returns None.

        Args:
            paper: Paper metadata

        Returns:
            Full text string or None if unavailable
        """
        if not paper.pubmed_id:
            return None

        # Try to get PMC full text via efetch
        await self._acquire_rate_limit()

        params = self._build_api_params({
            "db": "pmc",
            "id": paper.pubmed_id,
            "retmode": "xml",
            "rettype": "full",
        })

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/efetch.fcgi",
                params=params,
            )

            if response.status_code == 404:
                return None

            response.raise_for_status()

            # Extract text from PMC XML
            root = ET.fromstring(response.text)
            text_parts = []

            for elem in root.iter():
                if elem.text and elem.text.strip():
                    text_parts.append(elem.text.strip())

            if text_parts:
                return "\n\n".join(text_parts)

            return None

        except Exception as e:
            logger.debug(f"PubMed full text retrieval failed for {paper.pubmed_id}: {e}")
            return None

    async def get_related_papers(
        self,
        pmid: str,
        max_results: int = 50,
    ) -> AsyncIterator[PaperMetadata]:
        """
        Get papers related to a given PMID using elink.

        Args:
            pmid: PubMed ID
            max_results: Maximum related papers to return

        Yields:
            PaperMetadata for related papers
        """
        if pmid.startswith("pubmed:"):
            pmid = pmid[7:]

        await self._acquire_rate_limit()

        params = self._build_api_params({
            "dbfrom": "pubmed",
            "db": "pubmed",
            "id": pmid,
            "cmd": "neighbor_score",
            "retmode": "xml",
        })

        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/elink.fcgi",
                params=params,
            )
            response.raise_for_status()

            root = ET.fromstring(response.text)
            related_pmids = []

            for link in root.findall(".//Link"):
                id_elem = link.find("Id")
                if id_elem is not None and id_elem.text:
                    related_pmids.append(id_elem.text)
                    if len(related_pmids) >= max_results:
                        break

            if related_pmids:
                papers = await self._efetch(related_pmids)
                for paper in papers:
                    yield paper

        except Exception as e:
            logger.error(f"PubMed elink error: {e}")
