## SearXNG Image Search Deployment & API Integration Briefing

### 1. Viable Providers

**Self-Hosted SearXNG** (Recommended)[1][2][3]
- **Why reliable**: Open-source metasearch engine with built-in image proxy, aggregates results from multiple engines (DuckDuckGo, Bing, Google, etc.), fully customizable with no external rate limits on your own instance
- **URL**: Deploy via Docker at `http://your-domain:8888` or `https://searx.yourdomain.com`
- **Rate limit notes**: No limits on self-hosted instances; configurable `limiter: false` for private use[2][4]
- **Auth**: None required for your own instance

**Brave Search API**[5][6][7][8]
- **Why reliable**: Independent web index (not a metasearch), fast, privacy-focused with dedicated image search endpoint
- **URL**: `https://api.search.brave.com/res/v1/images/search`
- **Free tier**: 2,000 queries/month at 1 query/second[6][7]
- **Paid tiers**: Base ($5/1k requests, 20M/month, 20 qps) | Pro ($9/1k requests, unlimited, 50 qps)[9][6][7]
- **Auth**: API key required (sign up at https://api-dashboard.search.brave.com)[10][11][12]

**DuckDuckGo Direct** (Not Recommended for Production)
- **Why problematic**: Frequent 403/rate-limit errors[13][14][15], blocks automated requests aggressively, requires rotating proxies ($1.5-$4.99/GB)[16][17][18] and custom User-Agent headers[13][19] to bypass blocks
- **Workaround cost**: Residential proxy services start at ~$1.5/GB[16][17]

***

### 2. Integration Details

#### **SearXNG Configuration**

**Environment Variables**[20][21][22]:
```bash
SEARXNG_BASE_URL=https://searx.yourdomain.com
SEARXNG_SECRET=<generate with: openssl rand -hex 32>
SEARXNG_IMAGE_PROXY=true
```

**settings.yml** (mounted to `/etc/searxng/settings.yml`)[2][4][23][24]:
```yaml
use_default_settings: true

server:
  secret_key: "<your-secret>"  # or use SEARXNG_SECRET env var
  limiter: false  # disable for private/local instances
  image_proxy: true  # enables built-in image proxying

search:
  formats:
    - html
    - json  # REQUIRED for API access

ui:
  static_use_hash: true
```

**Docker Deployment**[1][3][25]:
```bash
docker run -d \
  --name searxng \
  -p 8888:8080 \
  -v ./config:/etc/searxng \
  -v .//var/cache/searxng \
  -e "SEARXNG_BASE_URL=http://localhost:8888" \
  -e "SEARXNG_SECRET=$(openssl rand -hex 32)" \
  searxng/searxng:latest
```

**Throttling/Quota**: None on self-hosted instances[2][25]

***

#### **Brave Search API Configuration**

**Environment Variables**:
```bash
BRAVE_SEARCH_API_KEY=<your-api-key>
BRAVE_SEARCH_ENDPOINT=https://api.search.brave.com/res/v1/images/search
```

**Authentication**: API key in `X-Subscription-Token` header[8][26][27][28]

**Image Search Request**[8][29][28]:
```bash
curl -s --compressed \
  "https://api.search.brave.com/res/v1/images/search?q=mountain+landscapes&count=20&safesearch=moderate" \
  -H "Accept: application/json" \
  -H "Accept-Encoding: gzip" \
  -H "X-Subscription-Token: <BRAVE_SEARCH_API_KEY>"
```

**Parameters**[8][29]:
- `q`: Search query (required)
- `count`: Number of results (default: 20)
- `safesearch`: `off`, `moderate`, `strict`
- `search_lang`: Language code (e.g., `en`)
- `country`: Country code (e.g., `US`)

**Rate Limits**[6][7]:
- Free: 1 qps, 2,000/month
- Base: 20 qps, 20M/month
- Pro: 50 qps, unlimited

**Signup**: https://api-dashboard.search.brave.com/login → Subscribe to plan → Generate API key[10][30][11]

***

#### **DuckDuckGo Rate-Limit Workaround** (If Absolutely Necessary)

**User-Agent Rotation**[13][19]:
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0"
}
```

**Rotating Proxy Services**[16][17][18]:
- Residential proxies ($1.5-$4.99/GB) from providers like GoProxy, SOAX, Novada
- Configure proxy rotation to distribute requests across IPs
- **Note**: Cost scales with usage; not economical for high-volume scraping

***

### 3. Validation Steps

#### **Verify SearXNG JSON API**[23][31][32][33][34]:
```bash
# Test basic connectivity
curl "http://localhost:8888/search?q=test&format=json"

# Test image search with categories
curl "http://localhost:8888/search?q=cats&format=json&categories=images"

# Alternative POST method
curl -X POST "http://localhost:8888/search" \
  --data-urlencode "q=test" \
  -d "format=json"
```

**Success indicators**[23][31]:
- Returns JSON object with `results`, `query`, `number_of_results` fields
- HTTP 200 status code
- No HTML tags in response

**Common failure modes**[35][36]:
- **403 Forbidden**: JSON format not enabled in `settings.yml` → Add `json` to `search.formats`[35]
- **500 Error**: Circular reference in certain categories (known bug with videos+json)[36] → Test with `categories=general` or `categories=images`
- **HTML response**: Restart container after modifying `settings.yml`[23][35]

***

#### **Verify Brave Search API**[8][26][28][12]:
```bash
# Test web search endpoint
curl "https://api.search.brave.com/res/v1/web/search?q=test" \
  -H "X-Subscription-Token: <BRAVE_SEARCH_API_KEY>" \
  -H "Accept: application/json"

# Test image search endpoint
curl "https://api.search.brave.com/res/v1/images/search?q=sunset&count=5" \
  -H "X-Subscription-Token: <BRAVE_SEARCH_API_KEY>" \
  -H "Accept: application/json"
```

**Success indicators**[8]:
- Returns JSON with `results` array containing image objects
- Each result has `title`, `url`, `thumbnail`, `properties` fields
- HTTP 200 status code

**Common failure modes**[27]:
- **SUBSCRIPTION_TOKEN_INVALID**: Wrong API key or wrong header name → Use `X-Subscription-Token` (not `Authorization`)[26][27]
- **429 Rate Limit**: Exceeded free tier quota → Upgrade plan or wait for monthly reset[6]
- **401 Unauthorized**: API key not registered or subscription not active[11]

***

#### **Integration with KITTY Vision Pipeline**

**Environment Configuration**:
```bash
# Option A: SearXNG
export SEARXNG_BASE_URL=http://localhost:8888
export IMAGE_SEARCH_PROVIDER=searxng

# Option B: Brave
export BRAVE_SEARCH_API_KEY=<your-key>
export BRAVE_SEARCH_ENDPOINT=https://api.search.brave.com/res/v1/images/search
export IMAGE_SEARCH_PROVIDER=brave
```

**Test API Call from KITTY**:
```bash
# SearXNG
curl "http://localhost:8888/search?q=mechanical+keyboard&format=json&categories=images" | jq '.results[:5]'

# Brave
curl "https://api.search.brave.com/res/v1/images/search?q=mechanical+keyboard&count=5" \
  -H "X-Subscription-Token: $BRAVE_SEARCH_API_KEY" | jq '.results[:5]'
```

**Expected workflow**: Query → Image search API → Present thumbnails → User selects reference → Vision model analyzes → CAD API call[Based on user context about KITTY prototype]

Sources
[1] GitHub - GridexX/SearXNG-Self-Hosted: Deploy your SearXNG instance in minutes https://github.com/GridexX/SearXNG-Self-Hosted/
[2] Dify保姆级教程(二)：手把手教你配置SearXNG搜索功能 https://blog.csdn.net/All_Empty/article/details/148337522
[3] Self-hosting SearXNG with Docker, Nginx, and SSL https://hrant.am/post/searxng_deployment/
[4] searxng/utils/templates/etc/searxng/settings.yml at master · searxng/searxng https://github.com/searxng/searxng/blob/master/utils/templates/etc/searxng/settings.yml
[5] brave-search/README.md at master · erik-balfe/brave-search https://github.com/erik-balfe/brave-search/blob/master/README.md
[6] Brave Search API https://brave.com/search/api/
[7] Pricing https://api-dashboard.search.brave.com/app/plans
[8] Image Search https://api-dashboard.search.brave.com/app/documentation/image-search/get-started
[9] Brave Launches AI Grounding API: Boosting Search Accuracy ... https://www.businesstechweekly.com/technology-news/brave-launches-ai-grounding-api-boosting-search-accuracy-for-smarter-ai-applications/
[10] Brave Search - Wildcard https://docs.wild-card.ai/tools/apis/brave
[11] No API key generated - Brave Community https://community.brave.app/t/no-api-key-generated/644606
[12] Brave Search MCP | MCP Link https://mcp-link.vercel.app/links/brave
[13] duckduckgo_search occurs 202 Ratelimit error · Issue #9045 https://github.com/langgenius/dify/issues/9045
[14] duckduckgo rate limit error · Issue #136 · crewAIInc/crewAI - GitHub https://github.com/crewAIInc/crewAI/issues/136
[15] DuckDuckGoSearchException: _aget_url() https://links.duckduckgo.com/d.js DuckDuckGoSearchException: Ratelimit https://stackoverflow.com/questions/78177662/duckduckgosearchexception-aget-url-https-links-duckduckgo-com-d-js-duckduc
[16] Scraper API for DuckDuckGo - Novada Proxy https://www.novada.com/guide/application-scenario/duckduckgo-scraper-api/
[17] DuckDuckGo Proxies - GoProxy https://www.goproxy.com/proxies-solutions/duckduckgo-proxies/
[18] Duckduckgo proxies - 191+ Million IPs in 195+ locations - SOAX https://soax.com/proxies/duckduckgo
[19] Set user agent in HTTP node to avoid 403 forbidden error while ... https://community.n8n.io/t/set-user-agent-in-http-node-to-avoid-403-forbidden-error-while-scraping/6993
[20] settings.yml: allow to base_url with the SEARXNG_BASE_URL env variable by dalf · Pull Request #990 · searxng/searxng https://github.com/searxng/searxng/pull/990
[21] Searxng Environment Variables https://www.genspark.ai/spark/searxng-environment-variables/f379a8b3-5d1c-4bae-a19e-9f4446045cc6
[22] settings.yml https://git.terminaldweller.com/scripts/plain/terminaldweller.com/searxng/searxng/settings.yml
[23] SearXNG启用JSON格式API实现大模型应用联网搜索功能开发_searxng api-... https://blog.csdn.net/weixin_65552509/article/details/149323853
[24] Get results in JSON format? · searxng/searxng · Discussion #1789 https://github.com/searxng/searxng/discussions/1789&rut=5ba4ed30f1bd16aa1daaf934ba24352b13edfd9bdbf6c0d1f4e607d9f40f07ad
[25] Installation container - SearXNG https://docs.searxng.org/admin/installation-docker.html
[26] Request Headers https://api-dashboard.search.brave.com/app/documentation/suggest/request-headers
[27] Configure Brave Search Agent - Recent Video - n8n https://thinktank.ottomator.ai/t/configure-brave-search-agent-recent-video/6960
[28] llama-cpp-search/brave_search.py at main · vatsalsaglani/llama-cpp-search https://github.com/vatsalsaglani/llama-cpp-search/blob/main/brave_search.py
[29] Brave Search API Wrapper - NPM https://www.npmjs.com/package/brave-search
[30] Quick Guide  Set Up Your Free Brave Search API Key #csgo #realwaystomakemoneyfromhome #techtok https://www.youtube.com/watch?v=kekK3JxUcek
[31] SearxNG Search API https://lagnchain.readthedocs.io/en/latest/ecosystem/searx.html
[32] SearxNG Search API - Docs by LangChain https://docs.langchain.com/oss/python/integrations/providers/searx
[33] SearxNG Search API | 🦜️🔗 LangChain https://python.langchain.com/v0.2/docs/integrations/providers/searx/
[34] SearXNG Search | liteLLM https://docs.litellm.ai/docs/search/searxng
[35] not returning json results, only html #3542 https://github.com/searxng/searxng/discussions/3542
[36] Something brokes SearXNG search api when i choose json format ... https://github.com/searxng/searxng/issues/2505
[37] Automated SearXNG deployment script for Ubuntu 24.04 (Docker + mDNS + dual HTTP/HTTPS) https://www.reddit.com/r/Searx/comments/1opbhu2/automated_searxng_deployment_script_for_ubuntu/
[38] changing settings in searxng https://www.reddit.com/r/selfhosted/comments/15abhxu/changing_settings_in_searxng/
[39] Brave Image Search https://academy.kuika.com/en/content/brave-image-search
[40] Integrate the Brave Search API API with the HTML to Image API - Pipedream https://pipedream.com/apps/brave-search-api/integrations/html-to-image
[41] settings.yml — SearXNG Documentation (2023.12.11+8a4104b99) https://dokk.org/documentation/searxng/2023-12-11-8a4104b9/admin/settings/settings/
[42] Brave Image Search URL https://forum.vivaldi.net/topic/76140/brave-image-search-url
[43] The docker-compose files for setting up a SearXNG ... https://github.com/searxng/searxng-docker
[44] settings.yml — SearXNG Documentation (2025.10.9+954f0f62b) https://docs.searxng.org/admin/settings/settings.html
[45] MxChat + Brave API: Smart Image & News Search Demo https://www.youtube.com/watch?v=7vDL5H7vToc
[46] SearXNG: Your Private Search Engine - Docker Tutorial https://www.youtube.com/watch?v=UBLypfM9U-g
[47] Settings — SearXNG Documentation (2025.11.7+b9b46431b) https://docs.searxng.org/admin/settings/index.html
[48] Brave Web Search API Proxy - API Plugin https://apiplugin.com/brave-search-api
[49] Ditch Google! - Ep. 4: Self-Hosting SearXNG with Portainer Stacks https://www.youtube.com/watch?v=ps8y1ewiRlY
[50] searxng/settings.yml · llamameta/564745675SearX5467tyereryyrty56NG4563475 at main https://huggingface.co/spaces/llamameta/564745675SearX5467tyereryyrty56NG4563475/blob/main/searxng/settings.yml
[51] 403 forbidden error when using requests even with setting the header to {'User-Agent': 'Mozilla/5.0'} on curseforge https://stackoverflow.com/questions/66832169/403-forbidden-error-when-using-requests-even-with-setting-the-header-to-user-a
[52] How to setup result proxy¶ https://tkmatrix.github.io/searxng/admin/morty.html
[53] Brave Unveils Free AI Grounding API https://digitalmarketingdesk.co.uk/brave-unveils-free-ai-grounding-api/
[54] server: — SearXNG Documentation (2025.5.30+37d851fb2) https://return42.github.io/searxng/admin/settings/settings_server.html
[55] Brave launches AI Grounding API - Free, Base, Pro tiers and ... https://www.etavrian.com/news/brave-ai-grounding-api-pricing-metrics
[56] Server https://docs.searxng.org/admin/settings/settings_server.html
[57] Don't use 403s or 404s for rate limiting https://developers.google.com/search/blog/2023/02/dont-404-my-yum
[58] Configuration | searxng/searxng | DeepWiki https://deepwiki.com/searxng/searxng/5.3-configuration
[59] Brave Search API Pricing 2025: Compare Plans and Costs https://www.trustradius.com/products/brave-search-api/pricing
[60] server: — SearXNG Documentation (2023.12.11+8a4104b99) https://dokk.org/documentation/searxng/2023-12-11-8a4104b9/admin/settings/settings_server/
[61] Brave launches AI Grounding API for agents - pricing, speed and ... https://www.etavrian.com/news/brave-ai-grounding-api-pricing-results
[62] searxng/settings.yml · ACRoot/SearXNG at main https://huggingface.co/spaces/ACRoot/SearXNG/blob/main/searxng/settings.yml
[63] What is DuckDuckGo-Favicons-Bot crawler bot https://datadome.co/bots/duckduckgo-favicons-bot/
[64] Overview https://brave-search-python-client.readthedocs.io/en/stable/main.html
[65] Get results in JSON format? #1789 - GitHub https://github.com/searxng/searxng/discussions/1789
[66] @tyr/brave-search - JSR https://jsr.io/@tyr/brave-search
[67] JSON Engine¶ https://return42.github.io/searxng/dev/engines/json_engine.html
[68] How to use proxy with DuckDuckGo? 2025 guide https://pixelscan.net/blog/how-to-use-proxy-with-duckduckgo-2025-guide/
[69] brave-search https://www.npmjs.com/package/brave-search?activeTab=readme
[70] 在 Docker 中运行 SearXNG 并启用 JSON API 访问 https://blog.csdn.net/weixin_42871919/article/details/144586503
[71] Extract DuckDuckGo Data with Crawlbase - Free Trial https://crawlbase.com/scrape-duckduckgo
[72] kayvane1/brave-api: Search for words, documents, images ... https://github.com/kayvane1/brave-api
[73] Search API — SearXNG Documentation (2025.11.7+b9b46431b) https://docs.searxng.org/dev/search_api.html
[74] How Rotating Proxies Boost Web Scraping & Online Privacy (Podacast🎙️) https://www.youtube.com/watch?v=k5FfKk1Sc6k
[75] Library Reference https://brave-search-python-client.readthedocs.io/en/latest/lib_reference.html
[76] Search API https://docs.searxng.org/dev/search_api.html?highlight=format
[77] GitHub - TechyNilesh/DeepImageSearch: DeepImageSearch is a Python library for fast and accurate image search. It offers seamless integration with Python, GPU support, and advanced capabilities for identifying complex image patterns using the Vision Transformer models. https://github.com/TechyNilesh/DeepImageSearch
[78] Natural language image search with a Dual Encoder https://keras.io/examples/vision/nl_image_search/
[79] Brave Search API - Free Public APIs for Developers https://openpublicapis.com/api/brave-search-api
[80] Vertex AI Vision https://cloud.google.com/vertex-ai-vision
[81] Installed a SearXNG but... https://www.reddit.com/r/selfhosted/comments/w2eury/installed_a_searxng_but/
[82] Integration with kitty's icat for previewing images? #3228 https://github.com/junegunn/fzf/issues/3228
[83] searxng-docker/searxng/settings.yml at master · searxng/searxng-docker https://github.com/searxng/searxng-docker/blob/master/searxng/settings.yml
[84] Brave Search - 雪球AI https://www.xueqiuai.com/en/825.html
[85] How to Use the kitty Object Detection API https://universe.roboflow.com/alina-jw6a5/kitty-g0jgn/model/1
[86] SearXNG | av/harbor | DeepWiki https://deepwiki.com/av/harbor/4.3.1-searxng
[87] Brave - Julep https://docs.julep.ai/integrations/search/brave
[88] Ximilar: Image Recognition & Visual Search API ... https://www.ximilar.com
[89] SearXNGをCloudRunでホスティングする｜sys1yagi https://note.com/sys1yagi/n/na49e73442afc
[90] Using cURL to Troubleshoot Agent Communication in SanerCVEM https://support.secpod.com/support/solutions/articles/1060000150847-using-curl-to-troubleshoot-agent-communication-in-sanercvem
[91] Brave Deep Research MCP https://glama.ai/mcp/servers/@suthio/brave-deep-research-mcp/blob/main/src/services/brave-search.ts
[92] SearxNG搜索API | 🦜️🔗 Langchain中文网 http://docs.autoinfra.cn/docs/integrations/providers/searx
[93] Integrate the Brave Search API API with the Token Metrics API https://pipedream.com/apps/brave-search-api/integrations/token-metrics
[94] Máy chủ MCP SearXNG https://lobehub.com/vi-VN/mcp/ninickname-searxng-mcp-server
[95] Answer CAPTCHA from server's IP https://docs.searxng.org/admin/answer-captcha.html
[96] Am I using JSON API right? (calling engines from the endpoint) https://www.reddit.com/r/Searx/comments/1cokv0g/am_i_using_json_api_right_calling_engines_from/
[97] Integrate the Brave Search API API with the PortaBilling API - Pipedream https://pipedream.com/apps/brave-search-api/integrations/portabilling
