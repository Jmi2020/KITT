# noqa: D401
"""WebTool for fetching and parsing web content."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify as md

logger = logging.getLogger(__name__)


class WebTool:
    """Fetch and parse web content into clean markdown.

    Provides high-quality web content extraction with:
    - User-agent rotation to avoid blocking
    - HTML to markdown conversion
    - Content cleaning (remove scripts, styles, nav, ads)
    - Metadata extraction (title, description, author)
    - Error handling for network issues
    """

    def __init__(
        self,
        timeout: int = 30,
        max_content_length: int = 10_000_000,  # 10MB
        user_agent: Optional[str] = None,
    ) -> None:
        """Initialize WebTool.

        Args:
            timeout: HTTP request timeout in seconds
            max_content_length: Maximum content size to download
            user_agent: Custom user agent string (uses default if not provided)
        """
        self.timeout = timeout
        self.max_content_length = max_content_length
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

    async def fetch(self, url: str) -> Dict[str, Any]:
        """Fetch and parse web content.

        Args:
            url: URL to fetch

        Returns:
            Dictionary with:
                - success (bool): Whether fetch succeeded
                - url (str): Original URL
                - final_url (str): Final URL after redirects
                - title (str): Page title
                - description (str): Meta description
                - author (str): Page author if available
                - content (str): Clean markdown content
                - raw_html (str): Raw HTML (optional)
                - error (str): Error message if failed
                - metadata (dict): Additional metadata
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
            ) as client:
                response = await client.get(url)
                response.raise_for_status()

                # Check content length
                content_length = len(response.content)
                if content_length > self.max_content_length:
                    return {
                        "success": False,
                        "url": url,
                        "error": f"Content too large: {content_length} bytes",
                        "metadata": {"content_length": content_length},
                    }

                # Parse HTML
                soup = BeautifulSoup(response.text, "lxml")

                # Extract metadata
                title = self._extract_title(soup)
                description = self._extract_description(soup)
                author = self._extract_author(soup)

                # Clean content
                cleaned_soup = self._clean_html(soup)

                # Convert to markdown
                markdown_content = md(
                    str(cleaned_soup),
                    heading_style="ATX",
                    bullets="-",
                    strip=["script", "style"],
                )

                return {
                    "success": True,
                    "url": url,
                    "final_url": str(response.url),
                    "title": title,
                    "description": description,
                    "author": author,
                    "content": markdown_content.strip(),
                    "metadata": {
                        "content_length": content_length,
                        "status_code": response.status_code,
                        "content_type": response.headers.get("content-type", ""),
                    },
                }

        except httpx.HTTPStatusError as exc:
            logger.error("HTTP error fetching %s: %s", url, exc)
            return {
                "success": False,
                "url": url,
                "error": f"HTTP {exc.response.status_code}: {exc.response.reason_phrase}",
                "metadata": {"status_code": exc.response.status_code},
            }

        except httpx.RequestError as exc:
            logger.error("Request error fetching %s: %s", url, exc)
            return {
                "success": False,
                "url": url,
                "error": f"Request failed: {str(exc)}",
                "metadata": {},
            }

        except Exception as exc:  # noqa: BLE001
            logger.error("Unexpected error fetching %s: %s", url, exc)
            return {
                "success": False,
                "url": url,
                "error": f"Unexpected error: {str(exc)}",
                "metadata": {},
            }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract page title from HTML.

        Tries in order:
        1. <title> tag
        2. og:title meta tag
        3. h1 tag
        4. URL path

        Args:
            soup: BeautifulSoup object

        Returns:
            Page title
        """
        # Try <title> tag
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        # Try og:title
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()

        # Try first h1
        h1 = soup.find("h1")
        if h1 and h1.string:
            return h1.string.strip()

        return "Untitled"

    def _extract_description(self, soup: BeautifulSoup) -> str:
        """Extract page description from meta tags.

        Args:
            soup: BeautifulSoup object

        Returns:
            Page description
        """
        # Try meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            return meta_desc["content"].strip()

        # Try og:description
        og_desc = soup.find("meta", property="og:description")
        if og_desc and og_desc.get("content"):
            return og_desc["content"].strip()

        return ""

    def _extract_author(self, soup: BeautifulSoup) -> str:
        """Extract author from meta tags.

        Args:
            soup: BeautifulSoup object

        Returns:
            Author name if found
        """
        # Try meta author
        meta_author = soup.find("meta", attrs={"name": "author"})
        if meta_author and meta_author.get("content"):
            return meta_author["content"].strip()

        # Try article:author
        article_author = soup.find("meta", property="article:author")
        if article_author and article_author.get("content"):
            return article_author["content"].strip()

        return ""

    def _clean_html(self, soup: BeautifulSoup) -> BeautifulSoup:
        """Clean HTML by removing non-content elements.

        Removes:
        - Scripts and styles
        - Navigation elements
        - Ads and promotional content
        - Comments
        - Hidden elements

        Args:
            soup: BeautifulSoup object

        Returns:
            Cleaned BeautifulSoup object
        """
        # Remove script and style elements
        for element in soup(["script", "style", "noscript"]):
            element.decompose()

        # Remove navigation elements
        for element in soup.find_all(["nav", "header", "footer", "aside"]):
            element.decompose()

        # Remove common ad/promo classes
        ad_classes = [
            "advertisement",
            "ad-container",
            "promo",
            "sidebar",
            "comments",
            "related-posts",
            "social-share",
            "newsletter",
        ]
        for class_name in ad_classes:
            for element in soup.find_all(class_=class_name):
                element.decompose()

        # Remove hidden elements
        for element in soup.find_all(style=lambda value: value and "display:none" in value):
            element.decompose()

        # Try to find main content area
        main_content = (
            soup.find("main")
            or soup.find("article")
            or soup.find(class_="content")
            or soup.find(id="content")
            or soup.find("body")
        )

        return main_content if main_content else soup

    def is_valid_url(self, url: str) -> bool:
        """Check if URL is valid and fetchable.

        Args:
            url: URL to validate

        Returns:
            True if URL is valid
        """
        try:
            parsed = urlparse(url)
            return bool(parsed.scheme in ("http", "https") and parsed.netloc)
        except Exception:  # noqa: BLE001
            return False


__all__ = ["WebTool"]
