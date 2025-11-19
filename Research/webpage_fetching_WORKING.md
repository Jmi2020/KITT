# Webpage Fetching System - WORKING

**Status:** ✅ FULLY FUNCTIONAL
**Date:** 2025-11-18
**Location:** Brain Service Research Pipeline

## Where Logs Are Located

### Primary Log Location
```bash
# Logs are written to files inside the brain container, NOT stdout
docker exec compose-brain-1 tail -f .logs/reasoning.log
```

### Why stdout/docker logs don't show research logs
- Research execution logs go to `.logs/reasoning.log` inside the container
- `docker logs compose-brain-1` only shows HTTP requests and scheduled jobs
- **Always check the file logs for research execution details**

## How To Access Research Logs

### Real-time monitoring
```bash
docker exec compose-brain-1 tail -f .logs/reasoning.log
```

### Search for specific sessions
```bash
docker exec compose-brain-1 grep "session-id" .logs/reasoning.log
```

### Check webpage fetching activity
```bash
docker exec compose-brain-1 grep -E "(🌐|✅ Fetched|📄 Combined)" .logs/reasoning.log
```

### Check claim extraction
```bash
docker exec compose-brain-1 grep -E "(Extracting claims|claims extracted)" .logs/reasoning.log
```

## Webpage Fetching Implementation

### Code Location
**File:** `/Users/Shared/Coding/KITT/services/brain/src/brain/research/graph/nodes.py`
**Lines:** 682-748

### Execution Flow

1. **Line 684:** `logger.info(f"🌐 Fetching full content from top {min(3, len(search_results))} search results")`
   - Indicates start of webpage fetching

2. **Lines 686-725:** Fetches top 3 search results
   - Uses `ToolType.FETCH_WEBPAGE` for each URL
   - Truncates to 3000 chars per page
   - Logs: `✅ Fetched {len(page_content)} chars from: {title[:60]}`

3. **Lines 727-737:** Combines fetched content
   - Merges all successfully fetched pages
   - Logs: `📄 Combined {len(full_contents)} full webpages, total {len(content)} chars`

4. **Lines 739-749:** Fallback to snippets
   - Only if ALL fetches fail
   - Logs: `No full content fetched, falling back to snippets`

### Example Log Output (Successful)

```
[INFO] WEB_SEARCH returned 3 results, total_results=10, filtered_count=0
[INFO] 🔍 DEBUG: About to check search_results, type=<class 'list'>, len=3, bool=True
[INFO] 🌐 Fetching full content from top 3 search results
[INFO] HTTP Request: GET https://www.healthline.com/nutrition/top-10-evidence-based-health-benefits-of-green-tea "HTTP/1.1 200 OK"
[INFO] ✅ Fetched 3027 chars from: 10 Evidence-Based Benefits of Green Tea - Healthline
[INFO] HTTP Request: GET https://health.clevelandclinic.org/green-tea-health-benefits "HTTP/1.1 200 OK"
[INFO] ✅ Fetched 3000 chars from: Green Tea Health Benefits - Cleveland Clinic
[INFO] HTTP Request: GET https://www.webmd.com/diet/health-benefits-green-tea "HTTP/1.1 200 OK"
[INFO] ✅ Fetched 3000 chars from: Health Benefits of Green Tea - WebMD
[INFO] 📄 Combined 3 full webpages, total 9027 chars
```

## Web Content Fetching Tool

### Implementation Location
**File:** `/Users/Shared/Coding/KITT/services/research/src/research/web_tool.py`
**Class:** `WebTool`

### Configuration

#### Environment Variables (in brain container)
```bash
JINA_READER_DISABLED=true      # Disables Jina Reader (avoid HTTP 402 errors)
JINA_READER_BASE_URL=https://r.jina.ai
JINA_API_KEY=jina_***          # API key (if enabled)
```

#### Current Configuration
- **Jina Reader:** DISABLED (to avoid payment errors)
- **Active Method:** BeautifulSoup + markdownify
- **Provider:** BeautifulSoup (shown in logs)

### Fetch Tool Details

**Tool Name:** `ToolType.FETCH_WEBPAGE`
**Executor:** `components.tool_executor.execute()`

#### Fetch Parameters
- `timeout`: 30 seconds
- `max_content_per_page`: 3000 chars (set in nodes.py line 706)
- `user_agent`: Mozilla/5.0 (Macintosh...)

#### Fallback Chain
1. **Primary:** Jina Reader (if enabled and API key valid)
2. **Fallback:** BeautifulSoup + markdownify
   - Fetches with httpx
   - Parses with BeautifulSoup (lxml parser)
   - Converts to markdown with markdownify
   - Returns metadata: `{"provider": "beautifulsoup"}`

## Test Results

### Test Sessions (2025-11-18)

| Session | Query | Webpages Fetched | Total Chars | Status |
|---------|-------|------------------|-------------|--------|
| 9f1f95ee | Language learning benefits | 3 | 7,880 | ✅ Success |
| b3d70533 | Exercise benefits | 3 | 9,538 | ✅ Success |
| 1e5e7c1c | Green tea benefits | 3 | 9,027 | ✅ Success |
| 61c22bc3 | Climate change causes | 2-3 | 6,480 | ✅ Success |

### Common Successful Sources
- Healthline.com (consistently 200 OK)
- ClevelandClinic.org (200 OK)
- WebMD.com (200 OK)
- PMC/NIH (200 OK)
- CDC.gov (200 OK)

### Failed Sources
- Cambridge.org (HTTP 403 Forbidden - Cloudflare challenge)
- Some academic sites with bot protection

## Known Issues

### Issue #1: Claims Not Being Extracted
- **Status:** OPEN
- **Description:** Despite successful webpage fetching (9000+ chars), claim extraction returns 0 claims
- **Location:** `services/brain/src/brain/research/extraction.py`
- **Next Steps:** Debug claim extraction with full webpage content

### Issue #2: Jina Reader HTTP 402
- **Status:** RESOLVED (disabled Jina)
- **Description:** Jina Reader API returns HTTP 402 (Payment Required)
- **Solution:** Set `JINA_READER_DISABLED=true`, use BeautifulSoup

### Issue #3: Database Persistence Issues
- **Status:** OPEN
- **Description:** Logs show findings persisted but API returns 0 findings
- **Errors:**
  - `value too long for type character varying(200)` (title truncation)
  - `invalid input syntax for type uuid: "research-system"`

## Verification Commands

### Verify webpage fetching is enabled
```bash
docker exec compose-brain-1 grep "🌐 Fetching full content" /app/services/brain/src/brain/research/graph/nodes.py
```

### Check environment configuration
```bash
docker exec compose-brain-1 printenv | grep JINA
```

### Monitor live research execution
```bash
docker exec compose-brain-1 tail -f .logs/reasoning.log | grep -E "(🌐|✅ Fetched|📄 Combined|WEB_SEARCH)"
```

### Check claim extraction attempts
```bash
docker exec compose-brain-1 grep -A 10 "📄 Combined" .logs/reasoning.log | grep -E "(claim|extract)"
```

## Summary

✅ **Webpage Fetching:** FULLY WORKING
✅ **Content Extraction:** BeautifulSoup successfully extracting 3000+ chars per page
✅ **Content Combining:** Successfully merging 2-3 pages into 6000-9500 char findings
❌ **Claim Extraction:** NOT WORKING - returns 0 claims despite full content
❌ **Database Persistence:** Findings not persisting correctly

**Next Priority:** Debug why claim extraction fails on full webpage content (9000+ chars)
