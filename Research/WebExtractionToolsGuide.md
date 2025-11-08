# Web Content Extraction Tools: Integration Guide for llama.cpp + Athene V2 Agent

## Overview

This guide covers **secondary tools** that complement web search for LLM agents. While search tools (SearXNG, Tavily, Brave) return URLs and snippets, these tools **fetch and extract full page content** so your agent can read entire articles, documents, and dynamic web pages.

---

## Why You Need Content Extraction Tools

**Web Search Returns:**
- Titles, URLs, and short snippets (~200 characters)
- Metadata about pages
- Search rankings

**Content Extraction Tools Provide:**
- Full article text (thousands of words)
- Markdown-formatted content
- Cleaned HTML without ads/navigation
- JavaScript-rendered dynamic content
- PDF and document parsing

**Typical Agent Workflow:**
1. Search for "quantum computing breakthroughs 2025"
2. Get list of URLs from search results
3. **Extract full content** from top 3 URLs
4. Analyze and synthesize comprehensive answer

---

## Tool Comparison Matrix

| Tool | Type | Cost | Dynamic Content | Setup | Best For |
|------|------|------|----------------|-------|----------|
| **Jina Reader API** | Cloud API | FREE (rate limited) | Yes | 1 min | Quick integration, free tier |
| **Firecrawl** | Cloud/Self-hosted | $8/1K pages or FREE self-hosted | Yes | 15 min | Production, AI-optimized |
| **BeautifulSoup** | Python library | FREE | No | 5 min | Static HTML, simple sites |
| **Playwright** | Browser automation | FREE | Yes | 10 min | Complex sites, full control |
| **Crawl4AI** | AI-optimized scraper | FREE | Yes | 10 min | LLM-focused extraction |
| **Trafilatura** | Content extractor | FREE | No | 5 min | Fast article extraction |

---

# Option 1: Jina Reader API (Recommended for Quick Start)

## Why Jina Reader?
- âœ… **FREE** - 20 RPM without key, 500 RPM with free key
- âœ… **Zero Setup** - Just add URL to API endpoint
- âœ… **LLM-Optimized** - Uses ReaderLM model for clean output
- âœ… **Multiple Formats** - Markdown, JSON, or text
- âœ… **Built-in Search** - Can search AND extract in one call

## Features

- Converts any URL to clean Markdown
- Removes ads, navigation, footers automatically
- Handles PDFs with PDF.js extraction
- Image captioning and alt-text
- Link deduplication
- Dynamic content rendering with headless Chrome

## Pricing & Rate Limits

| Tier | Cost | RPM | TPM | Use Case |
|------|------|-----|-----|----------|
| No API Key | FREE | 20 | Unlimited | Testing, hobby |
| Free API Key | FREE | 500 | Unlimited | Production, moderate volume |
| Premium Key | Pay per token | 5,000 | Unlimited | High volume |

**Token counting:** Based on output tokens (extracted content length)

**Cost example:** 1M output tokens â‰ˆ $0.20 (very cheap)

## Setup & Integration

### Step 1: Get Free API Key (Optional)

Visit: https://jina.ai/reader

Click "Get API Key" - instant, no credit card required.

### Step 2: Create Integration Function

Add to your existing agent code:

```python
import requests
from pydantic import BaseModel, Field
from typing import Optional

class JinaReader(BaseModel):
    """Fetch and read full content from any URL using Jina Reader API"""
    url: str = Field(..., description="URL to fetch and read")
    format: str = Field(default="markdown", description="Output format: 'markdown', 'text', or 'json'")

    def run(self):
        """Extract content using Jina Reader API"""
        try:
            # Jina Reader endpoint - prepend URL with r.jina.ai/
            api_url = f"https://r.jina.ai/{self.url}"

            headers = {
                "Accept": "application/json",
                "X-Return-Format": self.format
            }

            # Add API key if you have one (optional but recommended)
            api_key = os.environ.get("JINA_API_KEY")
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"

            response = requests.get(api_url, headers=headers, timeout=30)
            response.raise_for_status()

            data = response.json()

            return {
                "url": self.url,
                "title": data.get("data", {}).get("title", ""),
                "content": data.get("data", {}).get("content", ""),
                "description": data.get("data", {}).get("description", ""),
                "format": self.format,
                "usage": data.get("data", {}).get("usage", {})
            }

        except requests.exceptions.Timeout:
            return {"error": f"Timeout fetching {self.url}"}
        except Exception as e:
            return {"error": f"Failed to read {self.url}: {str(e)}"}
```

### Step 3: Add to Your Agent

```python
from llama_cpp_agent import FunctionCallingAgent, LlamaCppFunctionTool
from llama_cpp_agent.providers import LlamaCppServerProvider

# Your existing search tool
search_tool = LlamaCppFunctionTool(WebSearch)

# New Jina Reader tool
reader_tool = LlamaCppFunctionTool(JinaReader)

# Create agent with both tools
agent = FunctionCallingAgent(
    LlamaCppServerProvider("http://localhost:8080"),
    llama_cpp_function_tools=[
        search_tool,   # Search the web
        reader_tool    # Read full content
    ],
    messages_formatter_type=MessagesFormatterType.CHATML
)
```

### Step 4: Test It

```python
# Test reading a URL
if __name__ == "__main__":
    test_url = "https://arxiv.org/abs/2401.00001"

    reader = JinaReader(url=test_url, format="markdown")
    result = reader.run()

    print("Title:", result.get("title"))
    print("Content preview:", result.get("content")[:500])
```

## Direct API Usage (cURL)

```bash
# Simple usage - no API key
curl https://r.jina.ai/https://example.com

# With API key for higher rate limit
curl -H "Authorization: Bearer YOUR_API_KEY" \
     https://r.jina.ai/https://example.com

# Get JSON format
curl -H "X-Return-Format: json" \
     https://r.jina.ai/https://example.com

# Search AND extract content
curl https://s.jina.ai/quantum+computing+2025
```

## Advanced Features

### 1. Search + Extract Combined

Jina has a special endpoint that searches AND extracts full content:

```python
class JinaSearchAndRead(BaseModel):
    """Search the web and get full content from results"""
    query: str = Field(..., description="Search query")

    def run(self):
        """Search and extract full page content"""
        api_url = f"https://s.jina.ai/{self.query}"

        headers = {"Accept": "application/json"}
        api_key = os.environ.get("JINA_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        response = requests.get(api_url, headers=headers, timeout=60)
        data = response.json()

        return {
            "query": self.query,
            "results": data.get("data", [])[:5]  # Top 5 full articles
        }
```

**Note:** This costs 10,000 tokens per request (fixed).

### 2. Token Budget Control

```python
# Limit output tokens to save costs
headers = {
    "X-Return-Format": "markdown",
    "X-With-Generated-Alt": "true",  # AI-generated image descriptions
    "X-Target-Selector": "article",   # Only extract <article> tag
    "X-Timeout": "10"                 # Max wait time (seconds)
}
```

### 3. CSS Selector Filtering

```python
# Only extract specific sections
headers = {
    "X-Return-Format": "markdown",
    "X-Target-Selector": "article.main-content"  # CSS selector
}
```

## Cost Analysis

**Example Usage:**
- 1,000 article extractions per day
- Average article: 5,000 output tokens
- Total: 5M tokens/day = 150M tokens/month

**Cost:** ~$30/month at premium rates (or FREE with rate limiting)

**Comparison:**
- Firecrawl: ~$800/month (100K pages Ã— $8/1K)
- Jina: $30/month or FREE with 500 RPM
- Self-hosted: $0 but maintenance costs

### Best For:
- âœ… Quick integration (1 minute setup)
- âœ… Moderate to high volume (500 RPM free)
- âœ… Budget-conscious projects
- âœ… Clean, LLM-ready output
- âŒ NOT for sites requiring login/auth
- âŒ NOT for sites with complex anti-bot measures

---

# Option 2: Firecrawl (AI-Optimized, Production-Ready)

## Why Firecrawl?
- âœ… **AI-Optimized** - Built specifically for LLM agents
- âœ… **Schema-Driven** - Extract structured data with JSON schemas
- âœ… **Browser Fleet** - Handles JavaScript-heavy sites
- âœ… **Self-Hostable** - Free open-source alternative
- âœ… **Pagination Support** - Auto-click "next page" buttons

## Features

- Scrapes entire websites (multi-page crawling)
- Converts to Markdown, JSON, or screenshots
- LLM-based extraction using schemas
- JavaScript rendering with Chromium
- Anti-bot bypass (CAPTCHA solving, retries)
- Webhook notifications for long crawls

## Pricing

| Tier | Cost | Pages | Features |
|------|------|-------|----------|
| Free Trial | FREE | 500 pages | Full features |
| Hobby | $8/month | 1,000 pages | 2 concurrent browsers |
| Standard | $58/month | 10,000 pages | 10 concurrent browsers |
| Scale | $350/month | 100,000 pages | 50 concurrent browsers |
| Self-Hosted | FREE | Unlimited | DIY maintenance |

**Cost per page:** $0.008 (less than 1 cent per extraction)

## Cloud API Setup

### Step 1: Get API Key

Visit: https://firecrawl.dev

Sign up for free trial (500 pages free).

### Step 2: Install SDK

```bash
pip install firecrawl-py
```

### Step 3: Create Integration

```python
from firecrawl import FirecrawlApp
from pydantic import BaseModel, Field
import os

class FirecrawlScraper(BaseModel):
    """Scrape and extract content using Firecrawl"""
    url: str = Field(..., description="URL to scrape")
    formats: list = Field(default=["markdown"], description="Output formats: markdown, html, links")

    def run(self):
        """Extract content with Firecrawl"""
        try:
            api_key = os.environ.get("FIRECRAWL_API_KEY")
            if not api_key:
                return {"error": "FIRECRAWL_API_KEY not set"}

            app = FirecrawlApp(api_key=api_key)

            # Scrape single page
            result = app.scrape_url(
                self.url,
                params={
                    'formats': self.formats,
                    'onlyMainContent': True,  # Remove nav/footer/ads
                    'waitFor': 3000  # Wait 3s for JS to load
                }
            )

            return {
                "url": self.url,
                "title": result.get("metadata", {}).get("title", ""),
                "markdown": result.get("markdown", ""),
                "html": result.get("html", ""),
                "metadata": result.get("metadata", {})
            }

        except Exception as e:
            return {"error": f"Firecrawl error: {str(e)}"}

class FirecrawlCrawler(BaseModel):
    """Crawl entire website with Firecrawl"""
    url: str = Field(..., description="Website URL to crawl")
    max_pages: int = Field(default=10, description="Maximum pages to crawl")

    def run(self):
        """Crawl multi-page website"""
        try:
            api_key = os.environ.get("FIRECRAWL_API_KEY")
            app = FirecrawlApp(api_key=api_key)

            # Crawl website
            result = app.crawl_url(
                self.url,
                params={
                    'limit': self.max_pages,
                    'scrapeOptions': {
                        'formats': ['markdown'],
                        'onlyMainContent': True
                    }
                },
                poll_interval=5  # Check every 5s
            )

            return {
                "url": self.url,
                "pages_crawled": len(result.get("data", [])),
                "pages": [
                    {
                        "url": page.get("metadata", {}).get("sourceURL"),
                        "title": page.get("metadata", {}).get("title"),
                        "content": page.get("markdown", "")[:500]  # Preview
                    }
                    for page in result.get("data", [])
                ]
            }

        except Exception as e:
            return {"error": str(e)}
```

### Step 4: Add to Agent

```python
# Add Firecrawl tools
scraper_tool = LlamaCppFunctionTool(FirecrawlScraper)
crawler_tool = LlamaCppFunctionTool(FirecrawlCrawler)

agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[
        search_tool,      # Search
        scraper_tool,     # Scrape single page
        crawler_tool      # Crawl entire site
    ]
)
```

## Self-Hosted Setup (FREE)

### Prerequisites
- Docker and Docker Compose
- 2GB RAM minimum
- Redis (included in Docker setup)

### Step 1: Clone Repository

```bash
git clone https://github.com/mendableai/firecrawl.git
cd firecrawl
```

### Step 2: Configure Environment

Create `.env` file:

```bash
# .env
NUM_WORKERS_PER_QUEUE=8
PORT=3002
HOST=0.0.0.0

# Redis
REDIS_URL=redis://redis:6379
REDIS_RATE_LIMIT_URL=redis://redis:6379

# Optional: Playwright for JS rendering
PLAYWRIGHT_MICROSERVICE_URL=http://playwright-service:3000

# API Key (set your own)
FIRECRAWL_API_KEY=your-self-hosted-key-here
```

### Step 3: Launch with Docker

```bash
# Build and start
docker compose build
docker compose up -d

# Check logs
docker compose logs -f

# Verify it's running
curl http://localhost:3002/health
```

### Step 4: Test Self-Hosted API

```bash
# Scrape a page
curl -X POST http://localhost:3002/v1/scrape \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer your-self-hosted-key-here' \
  -d '{
    "url": "https://example.com",
    "formats": ["markdown"]
  }'
```

### Step 5: Python Client for Self-Hosted

```python
from firecrawl import FirecrawlApp

# Point to your self-hosted instance
app = FirecrawlApp(
    api_key="your-self-hosted-key-here",
    api_url="http://localhost:3002"  # Your server
)

result = app.scrape_url("https://example.com")
print(result.get("markdown"))
```

## Advanced Features

### 1. LLM-Based Extraction with Schemas

Extract structured data using LLM understanding:

```python
class FirecrawlExtractSchema(BaseModel):
    """Extract structured data from page using schema"""
    url: str = Field(..., description="URL to extract from")
    schema: dict = Field(..., description="JSON schema for extraction")

    def run(self):
        app = FirecrawlApp(api_key=os.environ["FIRECRAWL_API_KEY"])

        result = app.scrape_url(
            self.url,
            params={
                'formats': ['extract'],
                'extract': {
                    'schema': self.schema
                }
            }
        )

        return result.get("extract", {})

# Example usage
schema = {
    "type": "object",
    "properties": {
        "article_title": {"type": "string"},
        "author": {"type": "string"},
        "publish_date": {"type": "string"},
        "main_points": {
            "type": "array",
            "items": {"type": "string"}
        }
    }
}

extractor = FirecrawlExtractSchema(
    url="https://example.com/article",
    schema=schema
)
structured_data = extractor.run()
```

### 2. Map Entire Website

Get site structure before crawling:

```python
# Map website structure
map_result = app.map_url("https://example.com")

print("Sitemap:", map_result.get("links"))
```

### Best For:
- âœ… Production applications with budget
- âœ… Complex multi-page crawling
- âœ… Structured data extraction
- âœ… JavaScript-heavy sites
- âœ… Self-hosted for unlimited usage
- âŒ Overkill for simple single-page scraping
- âŒ More expensive than Jina for basic needs

---

# Option 3: BeautifulSoup + Requests (Simple & Free)

## Why BeautifulSoup?
- âœ… **FREE** - Python library, no API costs
- âœ… **Simple** - Easy to learn, widely documented
- âœ… **Fast** - Lightweight, no browser overhead
- âœ… **Flexible** - Full control over parsing
- âŒ **Static Only** - No JavaScript rendering

## Use Cases

**Good for:**
- Static HTML pages (blogs, news sites, Wikipedia)
- Fast, lightweight scraping
- Sites without JavaScript requirements

**NOT good for:**
- Single-page applications (React, Vue, Angular)
- Sites requiring login/cookies
- Pages with dynamic content loading

## Setup & Integration

### Step 1: Install Libraries

```bash
pip install beautifulsoup4 requests lxml html2text
```

### Step 2: Create Scraper Function

```python
import requests
from bs4 import BeautifulSoup
import html2text
from pydantic import BaseModel, Field
from typing import Optional

class BeautifulSoupScraper(BaseModel):
    """Fetch and parse HTML content (static pages only)"""
    url: str = Field(..., description="URL to scrape")
    selector: Optional[str] = Field(default=None, description="CSS selector for content")
    convert_to_markdown: bool = Field(default=True, description="Convert to markdown")

    def run(self):
        """Extract content using BeautifulSoup"""
        try:
            # Fetch page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(self.url, headers=headers, timeout=10)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'lxml')

            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()

            # Extract content
            if self.selector:
                content_element = soup.select_one(self.selector)
                if not content_element:
                    return {"error": f"Selector '{self.selector}' not found"}
                content = content_element
            else:
                # Try to find main content automatically
                content = (
                    soup.find('article') or 
                    soup.find('main') or 
                    soup.find('div', class_='content') or
                    soup.body
                )

            # Convert to text or markdown
            if self.convert_to_markdown:
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = False
                text_content = h.handle(str(content))
            else:
                text_content = content.get_text(separator='\n', strip=True)

            # Extract metadata
            title = soup.find('title')
            title_text = title.get_text(strip=True) if title else ""

            description = soup.find('meta', attrs={'name': 'description'})
            description_text = description.get('content', '') if description else ""

            return {
                "url": self.url,
                "title": title_text,
                "description": description_text,
                "content": text_content[:10000],  # Limit to 10K chars
                "content_length": len(text_content)
            }

        except requests.exceptions.Timeout:
            return {"error": f"Timeout fetching {self.url}"}
        except requests.exceptions.RequestException as e:
            return {"error": f"Request failed: {str(e)}"}
        except Exception as e:
            return {"error": f"Parsing failed: {str(e)}"}
```

### Step 3: Add to Agent

```python
soup_tool = LlamaCppFunctionTool(BeautifulSoupScraper)

agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[
        search_tool,
        soup_tool  # BeautifulSoup scraper
    ]
)
```

### Step 4: Test It

```python
# Test on a simple blog post
scraper = BeautifulSoupScraper(
    url="https://example.com/blog/post",
    selector="article.post-content",  # Optional: target specific element
    convert_to_markdown=True
)

result = scraper.run()
print(result.get("content"))
```

## Advanced Techniques

### 1. Extract Specific Elements

```python
# Extract only paragraphs
paragraphs = soup.find_all('p')
text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs])

# Extract links
links = [
    {"text": a.get_text(strip=True), "url": a.get('href')}
    for a in soup.find_all('a', href=True)
]

# Extract images
images = [
    {"alt": img.get('alt', ''), "src": img.get('src')}
    for img in soup.find_all('img')
]
```

### 2. Handle Pagination

```python
def scrape_paginated(base_url, max_pages=10):
    """Scrape multiple pages"""
    results = []

    for page_num in range(1, max_pages + 1):
        url = f"{base_url}?page={page_num}"

        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'lxml')

        # Extract articles from this page
        articles = soup.select('article.post')
        if not articles:
            break  # No more pages

        for article in articles:
            results.append({
                "title": article.find('h2').get_text(),
                "content": article.find('div', class_='content').get_text()
            })

        time.sleep(1)  # Be polite

    return results
```

### 3. Combine with Requests Session (for cookies/auth)

```python
session = requests.Session()

# Login
session.post('https://example.com/login', data={
    'username': 'user',
    'password': 'pass'
})

# Now scrape authenticated pages
response = session.get('https://example.com/private-page')
soup = BeautifulSoup(response.content, 'lxml')
```

## Performance Tips

```python
# Use connection pooling for multiple requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

session = requests.Session()
retry = Retry(total=3, backoff_factor=0.3)
adapter = HTTPAdapter(max_retries=retry)
session.mount('http://', adapter)
session.mount('https://', adapter)

# Faster parsing with lxml
soup = BeautifulSoup(html, 'lxml')  # Faster than 'html.parser'

# Limit content extraction
soup.find_all('p', limit=20)  # Only first 20 paragraphs
```

### Best For:
- âœ… Static HTML pages (blogs, news, documentation)
- âœ… Budget projects (completely free)
- âœ… Fast, lightweight scraping
- âœ… Full control over extraction logic
- âŒ NOT for JavaScript-rendered content
- âŒ NOT for complex anti-bot protection

---

# Option 4: Playwright (Dynamic Content, Full Browser)

## Why Playwright?
- âœ… **Dynamic Content** - Full browser, JavaScript rendering
- âœ… **User Interactions** - Click, scroll, fill forms
- âœ… **Multi-Browser** - Chrome, Firefox, WebKit
- âœ… **Screenshots** - Visual debugging
- âœ… **FREE** - Open-source library

## Features

- Renders JavaScript-heavy sites (React, Vue, Angular)
- Simulates user interactions (clicks, scrolling)
- Handles AJAX and lazy loading
- Takes screenshots and PDFs
- Network interception (block ads/trackers)
- Mobile device emulation

## Setup & Integration

### Step 1: Install Playwright

```bash
pip install playwright beautifulsoup4

# Install browsers
playwright install chromium  # Or firefox, webkit
```

### Step 2: Create Playwright Scraper

```python
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from typing import Optional
import time

class PlaywrightScraper(BaseModel):
    """Scrape dynamic content using Playwright browser automation"""
    url: str = Field(..., description="URL to scrape")
    wait_for_selector: Optional[str] = Field(
        default=None,
        description="CSS selector to wait for before extracting"
    )
    wait_time: int = Field(default=3, description="Wait time in seconds for JS to load")
    screenshot: bool = Field(default=False, description="Take screenshot")

    def run(self):
        """Extract content with full browser rendering"""
        try:
            with sync_playwright() as p:
                # Launch browser
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()

                # Set user agent to avoid detection
                page.set_extra_http_headers({
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                })

                # Navigate to page
                page.goto(self.url, wait_until='networkidle')

                # Wait for specific element if provided
                if self.wait_for_selector:
                    page.wait_for_selector(self.wait_for_selector, timeout=10000)
                else:
                    # Wait for general load
                    time.sleep(self.wait_time)

                # Get page content
                html_content = page.content()

                # Optional: Take screenshot
                screenshot_path = None
                if self.screenshot:
                    screenshot_path = f"/tmp/{hash(self.url)}.png"
                    page.screenshot(path=screenshot_path)

                browser.close()

                # Parse with BeautifulSoup
                soup = BeautifulSoup(html_content, 'lxml')

                # Remove unwanted elements
                for tag in soup(['script', 'style', 'nav', 'header', 'footer']):
                    tag.decompose()

                # Extract text
                text = soup.get_text(separator='\n', strip=True)

                # Get title
                title = soup.find('title')
                title_text = title.get_text(strip=True) if title else ""

                return {
                    "url": self.url,
                    "title": title_text,
                    "content": text[:10000],
                    "content_length": len(text),
                    "screenshot": screenshot_path,
                    "rendered": True
                }

        except Exception as e:
            return {"error": f"Playwright error: {str(e)}"}

class PlaywrightInteractive(BaseModel):
    """Interact with page (click, scroll, fill forms)"""
    url: str = Field(..., description="URL to visit")
    actions: list = Field(..., description="List of actions: [{'type': 'click', 'selector': '...'}]")

    def run(self):
        """Perform interactive scraping"""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(self.url, wait_until='networkidle')

                results = []

                # Execute actions
                for action in self.actions:
                    action_type = action.get('type')
                    selector = action.get('selector')

                    if action_type == 'click':
                        page.click(selector)
                        page.wait_for_load_state('networkidle')
                        results.append(f"Clicked {selector}")

                    elif action_type == 'fill':
                        value = action.get('value', '')
                        page.fill(selector, value)
                        results.append(f"Filled {selector} with '{value}'")

                    elif action_type == 'scroll':
                        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                        time.sleep(2)
                        results.append("Scrolled to bottom")

                    elif action_type == 'wait':
                        page.wait_for_selector(selector, timeout=10000)
                        results.append(f"Waited for {selector}")

                # Extract final content
                html = page.content()
                soup = BeautifulSoup(html, 'lxml')
                text = soup.get_text(separator='\n', strip=True)

                browser.close()

                return {
                    "url": self.url,
                    "actions_performed": results,
                    "content": text[:10000]
                }

        except Exception as e:
            return {"error": str(e)}
```

### Step 3: Add to Agent

```python
playwright_tool = LlamaCppFunctionTool(PlaywrightScraper)
interactive_tool = LlamaCppFunctionTool(PlaywrightInteractive)

agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[
        search_tool,
        playwright_tool,      # For dynamic content
        interactive_tool      # For interactions
    ]
)
```

### Step 4: Test Dynamic Site

```python
# Example: Scrape JavaScript-rendered content
scraper = PlaywrightScraper(
    url="https://example-spa.com",
    wait_for_selector="div.loaded-content",
    wait_time=5,
    screenshot=True
)

result = scraper.run()
print(result)

# Example: Click "Load More" button
interactive = PlaywrightInteractive(
    url="https://example.com/articles",
    actions=[
        {"type": "wait", "selector": "button.load-more"},
        {"type": "click", "selector": "button.load-more"},
        {"type": "wait", "selector": "article.new-content"}
    ]
)

result = interactive.run()
```

## Advanced Techniques

### 1. Infinite Scroll Handling

```python
def scrape_infinite_scroll(url, max_scrolls=10):
    """Scrape page with infinite scroll"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url)

        previous_height = 0

        for _ in range(max_scrolls):
            # Scroll to bottom
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(2)  # Wait for load

            # Check if new content loaded
            current_height = page.evaluate('document.body.scrollHeight')
            if current_height == previous_height:
                break  # No more content

            previous_height = current_height

        html = page.content()
        browser.close()

        return html
```

### 2. Block Ads and Trackers (Faster Loading)

```python
def scrape_with_blocking(url):
    """Scrape while blocking ads and trackers"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()

        # Block unnecessary resources
        context.route("**/*.{png,jpg,jpeg,gif,svg,css}", lambda route: route.abort())
        context.route("**/analytics.js", lambda route: route.abort())
        context.route("**/ads/*", lambda route: route.abort())

        page = context.new_page()
        page.goto(url, wait_until='domcontentloaded')

        html = page.content()
        browser.close()

        return html
```

### 3. Mobile Device Emulation

```python
def scrape_mobile_view(url):
    """Scrape mobile version of site"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # iPhone 12 emulation
        iphone = p.devices['iPhone 12']
        context = browser.new_context(**iphone)

        page = context.new_page()
        page.goto(url)

        html = page.content()
        browser.close()

        return html
```

## Performance Optimization

```python
# Reuse browser instance across multiple pages
class PlaywrightPool:
    def __init__(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)

    def scrape(self, url):
        page = self.browser.new_page()
        page.goto(url, wait_until='networkidle')
        html = page.content()
        page.close()
        return html

    def close(self):
        self.browser.close()
        self.playwright.stop()

# Usage
pool = PlaywrightPool()
html1 = pool.scrape("https://example1.com")
html2 = pool.scrape("https://example2.com")
pool.close()
```

### Best For:
- âœ… JavaScript-rendered sites (SPAs, React apps)
- âœ… Sites requiring interactions (clicks, scrolls)
- âœ… Infinite scroll / lazy loading
- âœ… Taking screenshots for debugging
- âœ… Complex authentication flows
- âŒ Slower than static scraping
- âŒ Higher resource usage (browser overhead)

---

# Option 5: Crawl4AI (LLM-Optimized, Open Source)

## Why Crawl4AI?
- âœ… **FREE** - Open-source Python library
- âœ… **LLM-Focused** - Designed for AI agents
- âœ… **Auto-Markdown** - Converts HTML to clean Markdown
- âœ… **Smart Extraction** - LLM-guided content selection
- âœ… **Fast** - Async crawling, caching

## Features

- Automatic HTML-to-Markdown conversion
- LLM-guided extraction with prompts
- JavaScript rendering support
- Content filtering and chunking
- Multi-URL concurrent crawling
- CSS-based and semantic extraction

## Setup & Integration

### Step 1: Install Crawl4AI

```bash
pip install crawl4ai
playwright install  # Required for JS rendering
```

### Step 2: Create Integration

```python
from crawl4ai import WebCrawler
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from pydantic import BaseModel, Field
from typing import Optional

class Crawl4AIScraper(BaseModel):
    """Scrape content with Crawl4AI (LLM-optimized)"""
    url: str = Field(..., description="URL to crawl")
    extraction_prompt: Optional[str] = Field(
        default=None,
        description="LLM prompt for guided extraction"
    )

    def run(self):
        """Extract content using Crawl4AI"""
        try:
            crawler = WebCrawler()
            crawler.warmup()

            if self.extraction_prompt:
                # LLM-guided extraction
                strategy = LLMExtractionStrategy(
                    prompt=self.extraction_prompt,
                    # Use your local llama.cpp endpoint
                    api_base="http://localhost:8080/v1",
                    model="athene-v2-agent"
                )
                result = crawler.run(url=self.url, extraction_strategy=strategy)
                content = result.extracted_content
            else:
                # Standard markdown conversion
                result = crawler.run(url=self.url)
                content = result.markdown

            return {
                "url": self.url,
                "title": result.title,
                "markdown": content,
                "links": result.links[:10],  # Top 10 links
                "media": result.media[:5],   # Top 5 images
                "success": result.success
            }

        except Exception as e:
            return {"error": f"Crawl4AI error: {str(e)}"}
```

### Step 3: Advanced LLM Extraction

```python
class Crawl4AIStructuredExtraction(BaseModel):
    """Extract structured data using LLM understanding"""
    url: str = Field(..., description="URL to extract from")
    schema: dict = Field(..., description="Desired output schema")

    def run(self):
        """LLM-guided structured extraction"""
        try:
            crawler = WebCrawler()
            crawler.warmup()

            # Create prompt from schema
            prompt = f"""
            Extract information from this page in the following structure:
            {schema}

            Return only valid JSON matching this structure.
            """

            strategy = LLMExtractionStrategy(
                prompt=prompt,
                api_base="http://localhost:8080/v1",
                model="athene-v2-agent"
            )

            result = crawler.run(url=self.url, extraction_strategy=strategy)

            # Parse JSON response
            import json
            structured_data = json.loads(result.extracted_content)

            return {
                "url": self.url,
                "data": structured_data,
                "success": True
            }

        except Exception as e:
            return {"error": str(e)}
```

### Step 4: Add to Agent

```python
crawl4ai_tool = LlamaCppFunctionTool(Crawl4AIScraper)

agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[
        search_tool,
        crawl4ai_tool  # LLM-optimized scraper
    ]
)
```

## Advanced Features

### 1. Multi-URL Concurrent Crawling

```python
async def crawl_multiple_urls(urls):
    """Crawl multiple pages concurrently"""
    from crawl4ai import AsyncWebCrawler

    async with AsyncWebCrawler() as crawler:
        results = await crawler.arun_many(urls, max_concurrent=5)

        return [
            {
                "url": r.url,
                "markdown": r.markdown,
                "title": r.title
            }
            for r in results
        ]

# Usage
import asyncio
urls = ["https://example1.com", "https://example2.com"]
results = asyncio.run(crawl_multiple_urls(urls))
```

### 2. CSS-Based Extraction

```python
from crawl4ai.extraction_strategy import CosineStrategy

# Extract only specific sections
strategy = CosineStrategy(
    semantic_filter="article content only, no navigation",
    word_count_threshold=50,
    max_dist=0.2
)

crawler = WebCrawler()
result = crawler.run(
    url="https://example.com",
    extraction_strategy=strategy
)
```

### 3. Caching for Repeated Crawls

```python
# Enable caching
crawler = WebCrawler(verbose=True)
result = crawler.run(
    url="https://example.com",
    bypass_cache=False,  # Use cache if available
    cache_mode="write_only"  # or "read_only" or "disabled"
)
```

### Best For:
- âœ… LLM-focused applications
- âœ… Semantic content extraction
- âœ… Concurrent multi-page crawling
- âœ… Clean Markdown output
- âœ… Local LLM integration
- âŒ Less mature than Playwright
- âŒ Requires local LLM for best results

---

# Option 6: Trafilatura (Fast Article Extraction)

## Why Trafilatura?
- âœ… **FREE** - Python library
- âœ… **Fast** - Optimized for speed
- âœ… **Article-Focused** - Best for news/blog content
- âœ… **Simple** - One function call
- âœ… **Minimal Dependencies**

## Setup & Integration

```bash
pip install trafilatura
```

```python
import trafilatura
from pydantic import BaseModel, Field

class TrafilaturaExtractor(BaseModel):
    """Fast article content extraction with Trafilatura"""
    url: str = Field(..., description="URL to extract article from")
    output_format: str = Field(default="markdown", description="Format: markdown, txt, json, xml")

    def run(self):
        """Extract main article content"""
        try:
            # Download page
            downloaded = trafilatura.fetch_url(self.url)

            if not downloaded:
                return {"error": f"Failed to download {self.url}"}

            # Extract content
            if self.output_format == "markdown":
                content = trafilatura.extract(
                    downloaded,
                    output_format="markdown",
                    include_comments=False,
                    include_tables=True
                )
            elif self.output_format == "json":
                content = trafilatura.extract(
                    downloaded,
                    output_format="json",
                    with_metadata=True
                )
            else:
                content = trafilatura.extract(downloaded)

            return {
                "url": self.url,
                "content": content,
                "format": self.output_format
            }

        except Exception as e:
            return {"error": str(e)}
```

### Best For:
- âœ… News articles and blog posts
- âœ… Fast, lightweight extraction
- âœ… Simple use cases
- âŒ NOT for dynamic content
- âŒ NOT for complex layouts

---

# Complete Multi-Tool Agent Example

Here's a production-ready agent with all tools:

```python
from llama_cpp_agent import FunctionCallingAgent, MessagesFormatterType, LlamaCppFunctionTool
from llama_cpp_agent.providers import LlamaCppServerProvider

# Import all your tool classes
from search_tools import WebSearch  # From previous guide
from jina_reader import JinaReader
from firecrawl_scraper import FirecrawlScraper
from beautifulsoup_scraper import BeautifulSoupScraper
from playwright_scraper import PlaywrightScraper
from crawl4ai_scraper import Crawl4AIScraper
from trafilatura_extractor import TrafilaturaExtractor

# Create provider
provider = LlamaCppServerProvider("http://localhost:8080")

# Create all tools
search_tool = LlamaCppFunctionTool(WebSearch)
jina_tool = LlamaCppFunctionTool(JinaReader)
firecrawl_tool = LlamaCppFunctionTool(FirecrawlScraper)
soup_tool = LlamaCppFunctionTool(BeautifulSoupScraper)
playwright_tool = LlamaCppFunctionTool(PlaywrightScraper)
crawl4ai_tool = LlamaCppFunctionTool(Crawl4AIScraper)
trafilatura_tool = LlamaCppFunctionTool(TrafilaturaExtractor)

# System prompt with tool guidance
system_prompt = """You are an advanced research assistant with web search and content extraction capabilities.

AVAILABLE TOOLS:
1. web_search - Search the web for URLs and snippets
2. jina_reader - Fast, clean extraction (best for most pages)
3. firecrawl_scraper - AI-optimized, multi-page crawling
4. beautifulsoup_scraper - Simple static HTML extraction
5. playwright_scraper - Dynamic JavaScript-rendered pages
6. crawl4ai_scraper - LLM-guided extraction
7. trafilatura_extractor - Fast article extraction

STRATEGY:
- Use web_search first to find relevant URLs
- Choose extraction tool based on site type:
  * Simple blogs/news: jina_reader or trafilatura_extractor
  * JavaScript-heavy (React/Vue): playwright_scraper
  * Multi-page content: firecrawl_scraper
  * LLM-guided extraction: crawl4ai_scraper
  * Budget/simple: beautifulsoup_scraper

- Extract full content from top 2-3 URLs
- Synthesize comprehensive answer with citations
"""

# Create agent with all tools
agent = FunctionCallingAgent(
    provider,
    llama_cpp_function_tools=[
        search_tool,
        jina_tool,
        firecrawl_tool,
        soup_tool,
        playwright_tool,
        crawl4ai_tool,
        trafilatura_tool
    ],
    send_message_to_user_callback=lambda x: print(f"\nAgent: {x}"),
    messages_formatter_type=MessagesFormatterType.CHATML,
    system_prompt=system_prompt,
    allow_parallel_function_calling=False
)

# Test
if __name__ == "__main__":
    query = "What are the latest developments in quantum computing? Read full articles to provide detailed answer."
    print(f"User: {query}")
    agent.generate_response(query)
```

---

# Decision Matrix: Which Tool to Use?

| Scenario | Recommended Tool | Why |
|----------|------------------|-----|
| Quick integration, moderate volume | **Jina Reader API** | Free, fast setup, good quality |
| Production app with budget | **Firecrawl** | Reliable, AI-optimized, multi-page |
| Static HTML blogs/news | **BeautifulSoup** or **Trafilatura** | Fast, free, simple |
| JavaScript-heavy SPAs | **Playwright** | Full browser, handles dynamic content |
| Complex multi-page sites | **Firecrawl** (crawl mode) | Built for multi-page extraction |
| LLM-guided extraction | **Crawl4AI** | Semantic understanding, local LLM |
| Budget-constrained | **BeautifulSoup** + **Trafilatura** | Completely free, no API costs |
| Maximum reliability | **Jina** (primary) + **Firecrawl** (fallback) | Redundancy with different strengths |

---

# Cost Comparison

## Monthly Costs (100K page extractions)

| Tool | Setup | Monthly Cost | Notes |
|------|-------|--------------|-------|
| Jina Reader | 1 min | $0-20 | Free tier sufficient for most |
| Firecrawl Cloud | 5 min | $800 | $8 per 1K pages |
| Firecrawl Self-Hosted | 1 hour | $10 | VPS hosting only |
| BeautifulSoup | 5 min | $0 | Completely free |
| Playwright | 10 min | $0 | Free, but VPS costs if cloud |
| Crawl4AI | 10 min | $0 | Free, uses local LLM |
| Trafilatura | 5 min | $0 | Completely free |

**Recommended Budget Setup:**
- Primary: Jina Reader (free tier, 500 RPM)
- Backup: BeautifulSoup (free, unlimited)
- Special cases: Playwright (free, for JS sites)
- **Total: $0/month** for moderate usage

**Recommended Production Setup:**
- Primary: Jina Reader (paid tier, $20/mo)
- Secondary: Firecrawl self-hosted ($10/mo VPS)
- Fallback: BeautifulSoup (free)
- **Total: $30/month** for high reliability

---

# Troubleshooting

## Issue: Content Extraction Returns Garbage

**Cause:** Page uses JavaScript rendering

**Solution:** Switch from BeautifulSoup to Playwright:
```python
# Instead of BeautifulSoup
soup_tool = BeautifulSoupScraper(url=url)

# Use Playwright
playwright_tool = PlaywrightScraper(url=url, wait_time=5)
```

## Issue: Rate Limited by Target Site

**Solution:** Add delays and rotation:
```python
import time
import random

def scrape_with_delay(urls):
    results = []
    for url in urls:
        result = scraper.run(url)
        results.append(result)
        time.sleep(random.uniform(2, 5))  # Random 2-5s delay
    return results
```

## Issue: CAPTCHA Blocking

**Solutions:**
1. Use Jina Reader or Firecrawl (they handle CAPTCHAs)
2. Add proxies to Playwright
3. Slow down request rate
4. Use authenticated sessions

## Issue: Memory Overflow with Large Pages

**Solution:** Limit content extraction:
```python
# Limit to first 10,000 characters
content = content[:10000]

# Or extract only specific sections
soup.find('article').get_text()
```

---

# Next Steps

1. **Start with Jina Reader** - Easiest integration
2. **Add BeautifulSoup** - Free fallback for simple sites
3. **Add Playwright** - For JavaScript-heavy sites
4. **Test with your agent** - Run on various sites
5. **Monitor costs** - Track API usage
6. **Optimize** - Add caching, rate limiting

---

# Complete Integration Checklist

- [ ] Choose primary extraction tool (Jina recommended)
- [ ] Install dependencies (`pip install ...`)
- [ ] Create extraction function with Pydantic model
- [ ] Add tool to agent with `LlamaCppFunctionTool`
- [ ] Test on sample URLs
- [ ] Add error handling and retries
- [ ] Implement rate limiting
- [ ] Add fallback tools for reliability
- [ ] Monitor token usage and costs
- [ ] Document tool selection logic for team

---

*Guide created for llama.cpp with Athene V2 Agent*
*Last updated: November 2025*