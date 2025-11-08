## Best Web Search Tools for LLMs: MCP and Alternative Options for Self-Hosted Systems

When adding web search capabilities to self-hosted LLMs, you have two main approaches: **MCP (Model Context Protocol)** servers and traditional **function calling/tool integration** methods. Both offer unique advantages depending on your infrastructure and requirements.

### MCP Web Search Servers

MCP is an open standard introduced by Anthropic that provides a universal protocol for connecting AI models to external tools and data sources[1][2]. Here are the top MCP web search options:

#### **1. SearXNG MCP Server**

SearXNG is the most privacy-focused and self-hosted friendly option[3][4][5].

**Key Features:**
- Zero-configuration setup with automatic public instance selection
- Self-hosted metasearch engine support with optional authentication
- Aggregates results from multiple search engines
- Completely privacy-respecting with no tracking[6]
- Markdown-formatted results
- Configurable via environment variables (SEARXNG_URL, SEARXNG_USERNAME, SEARXNG_PASSWORD)[7]

**Best for:** Privacy-conscious users who want complete control over their search infrastructure and don't want queries sent to third parties[5].

**Installation:**
```bash
npm install searxngmcp
```

Configure in your MCP client with optional private instance support[3].

#### **2. Tavily MCP Server**

Tavily is purpose-built for AI agents and provides production-ready search capabilities[8][9][10].

**Key Features:**
- AI-optimized search with content extraction and filtering
- Real-time web search, extract, map, and crawl tools[10]
- Direct answer generation with supporting evidence
- Recent news search with AI-extracted content
- Customizable search depth (basic/advanced)[11]
- Domain filtering and time range controls[12]

**Best for:** Production applications requiring high-quality, AI-ready search results with minimal post-processing[13][14].

**Pricing:** $8-10 per 1,000 searches[14][15].

#### **3. Brave Search MCP Server**

Brave offers a privacy-first search API with an independent web index[16][17][18].

**Key Features:**
- Web, local business, image, video, and news search
- Privacy-focused with no user tracking[14]
- Multiple result filtering options
- Smart fallbacks (local to web search)[18]
- AI/data licensing friendly[19]

**Best for:** Developers who want privacy without sacrificing search quality, with good AI-specific features[20][15].

**Free Tier:** 2,000 calls per month[14][19].

#### **4. Web Search MCP Server (Open Source)**

A community-built MCP server supporting multiple search engines[21][22].

**Key Features:**
- Multi-engine support: Bing → Brave → DuckDuckGo fallback strategy[21]
- Full page content extraction with concurrent processing
- No API keys required for basic operation[21]
- Browser-based and HTTP request methods
- Playwright/Firefox integration for complex pages

**Best for:** Users wanting a free, self-contained solution without API dependencies.

### Alternative Integration Methods (Non-MCP)

If you're running self-hosted LLMs like Ollama or llama.cpp, you have several integration options:

#### **Function Calling / Tool Use**

Modern local LLMs support OpenAI-compatible function calling[23][24][25]:

**llama.cpp Integration:**
- Supports tool calling and structured outputs with fine-tuned models[24][26]
- Use with LangChain for agent frameworks[27]
- Bind tools using `llama-cpp-python` library[26]
- Models like Llama 3.1, Mistral, and Nous Research fine-tunes support this[24]

**Ollama Integration:**
- Native tool calling support in Ollama[25][28][29]
- Built-in web search API (requires Ollama API key)[25]
- Works with Tavily, Brave Search, or SerpAPI through function definitions[30]
- Can be combined with MCP through bridges like MCPHost[31][32]

#### **Framework-Based Integration**

**AnythingLLM:**
- Built-in web search and scraping agents[33][34][35]
- Supports DuckDuckGo, Google, SearchApi, Serper, Bing, Serply[35]
- Agent skills for automated web access[36]
- Can integrate with self-hosted LLMs (Ollama, llama.cpp)[34]

**Open WebUI:**
- Direct SearXNG integration for privacy-focused search[37][38][39]
- RAG web search functionality[40]
- Docker-compose configuration for easy setup[41]
- Function/tool system for custom integrations[38]

**n8n Workflows:**
- Self-hosted automation with unlimited search[42]
- SearXNG integration for free, unlimited queries
- Visual workflow builder for complex search pipelines[42]

### Comparison: MCP vs Function Calling

**MCP Advantages:**[1][2][43]
- Model-agnostic: works with any MCP-compatible client
- Persistent connections with stateful context
- Standardized protocol across tools
- Easier to swap AI providers without code changes
- Better separation of concerns (tools live independently)

**Function Calling Advantages:**[1][43]
- Simpler for single-provider setups
- Lower overhead for isolated API calls
- Tighter integration with specific LLM features
- More control over execution flow

### Best Web Search APIs for Self-Hosted LLMs

If you're building custom integrations, here's how the major APIs compare:

**Free/Low-Cost Options:**
1. **SearXNG** (self-hosted): Unlimited, free, privacy-focused[42]
2. **Brave Search**: 2,000 free calls/month[14][19]
3. **Tavily**: 1,000 free credits/month[14][19]
4. **Firecrawl**: Free tier available with AI-optimized results[14]

**Production-Grade Options:**
1. **Tavily** ($8-10/1k): Best for RAG, optimized for AI[14][44]
2. **Exa** ($1.50/1k): Fast semantic search, good for similarity[45][44]
3. **Brave Search** ($3-5/1k): Privacy + quality balance[15][44]
4. **Serper** ($3/1k): Fast Google SERP data[14]

### Integration Recommendations for Self-Hosted LLMs

**For llama.cpp:**
1. Use llama-server with tool calling support (`--jinja` flag)[46][27]
2. Integrate SearXNG for free unlimited search[47]
3. Build custom FastAPI wrapper for search APIs[47]
4. Use LangChain + Tavily/Brave for production[27]

**For Ollama:**
1. Use MCPHost as a bridge to MCP servers[31][32]
2. Leverage native Ollama tool calling[25][29]
3. Integrate with Open WebUI + SearXNG[37][38]
4. Use Tome for one-click MCP server management[31]

**For Production Applications:**
1. Start with Tavily MCP for reliability and AI-optimization[13][8]
2. Add Brave Search for privacy-conscious queries[16][48]
3. Self-host SearXNG as a free fallback[3][5]
4. Use Docker containers for MCP server isolation[49][50]

### Setting Up MCP with Self-Hosted LLMs

Since native MCP support is limited in Ollama and llama.cpp, you'll need bridging tools:

**MCPHost** (recommended for Ollama)[32]:
```bash
go install github.com/mark3labs/mcphost@latest
```

Configure `~/.mcphost.json` with your MCP servers and run:
```bash
mcphost --model llama3:8b "your query here"
```

**Docker-based MCP Servers**[49][50]:
```bash
git clone https://github.com/modelcontextprotocol/servers.git
./build_servers.sh
```

Configure your client to use Docker containers for each MCP server[49][51].

**LlamaIndex MCP Integration**[52]:
Build a local MCP client using LlamaIndex that connects to your llama.cpp or Ollama server and routes tool calls through MCP[52].

### Conclusion

For **maximum privacy and cost savings**, self-host **SearXNG** with an MCP server wrapper[3][5][42]. For **production reliability**, use **Tavily MCP**[8][10] with **Brave Search** as a backup[16][48]. If you're using **Ollama**, integrate via **MCPHost**[32] or **Open WebUI + SearXNG**[37][38]. For **llama.cpp**, implement function calling with **LangChain** and your choice of search APIs[24][27].

The combination of MCP's standardization and self-hosted search engines like SearXNG gives you the best of both worlds: privacy, unlimited usage, and future-proof integrations that work across any LLM platform[5][46][42].

Sources
[1] MCP vs Function Calling, Plugins, APIs - IKANGAI https://www.ikangai.com/model-context-protocol-comparison-mcp-vs-function-calling-plugins-apis/
[2] OpenAI Function Calling vs Anthropic Model Context Protocol (MCP ... https://www.linkedin.com/pulse/openai-function-calling-vs-anthropic-model-context-protocol-liu-pdj3e
[3] tisDDM/searxng-mcp - GitHub https://github.com/tisDDM/searxng-mcp
[4] SearXNG MCP: Privacy-Focused AI Web Search https://mcpmarket.com/server/searxng-2
[5] Jay4242's SearxNG MCP Server: The Privacy-First Search Tool ... https://skywork.ai/skypage/en/searxng-mcp-server-privacy-search/1978337427664007168
[6] This is my favorite MCP server to use with my local LLM https://www.xda-developers.com/favorite-mcp-server-use-local-llm/
[7] SearXNG MCP Server - LobeHub https://lobehub.com/mcp/tisddm-searxng-mcp
[8] Tavily MCP Server https://mcpservers.org/servers/altinakseven/tavily-mcp-server
[9] RamXX/mcp-tavily: An MCP server for Tavily's search API - GitHub https://github.com/RamXX/mcp-tavily
[10] tavily-ai/tavily-mcp: Production ready MCP server with real ... - GitHub https://github.com/tavily-ai/tavily-mcp
[11] tavily-search-mcp-server - Glama https://glama.ai/mcp/servers/@apappascs/tavily-search-mcp-server
[12] Tavily MCP Server | FlowHunt https://www.flowhunt.io/mcp-servers/tavily-search/
[13] Introducing the Parallel Search API | Build the world wide web for AIs https://parallel.ai/blog/introducing-parallel-search
[14] 7 Free Web Search APIs for AI Agents - KDnuggets https://www.kdnuggets.com/7-free-web-search-apis-for-ai-agents
[15] How does the Brave Search API compare to other Web search API ... https://brave.com/search/api/guides/what-sets-brave-search-api-apart/
[16] Brave Search MCP Server - GitHub https://github.com/brave/brave-search-mcp-server
[17] mikechao/brave-search-mcp: An MCP Server implementation that ... https://github.com/mikechao/brave-search-mcp
[18] @modelcontextprotocol/server-brave-search - NPM https://www.npmjs.com/package/@modelcontextprotocol/server-brave-search
[19] AI app developers: Tavily, Exa, and Brave Search API alternatives to ... https://www.linkedin.com/posts/aashishpahwa_if-youre-building-an-ai-app-these-apis-activity-7369360568471711746-56BN
[20] Brave Search API https://brave.com/search/api/
[21] A simple, locally hosted Web Search MCP server for use ... - GitHub https://github.com/mrkrsl/web-search-mcp
[22] Web Search MCP Server for use with Local LLMs - LobeHub https://lobehub.com/mcp/mrkrsl-web-search-mcp
[23] Function Calling with Open-Source LLMs - BentoML https://www.bentoml.com/blog/function-calling-with-open-source-llms
[24] Local Tool Calling with llamacpp - YouTube https://www.youtube.com/watch?v=rsDlu-9UP00
[25] Web search - Ollama's documentation https://docs.ollama.com/capabilities/web-search
[26] Llama.cpp - Docs by LangChain https://docs.langchain.com/oss/python/integrations/chat/llamacpp
[27] Building AI Agents with llama.cpp - KDnuggets https://www.kdnuggets.com/building-ai-agent-with-llama-cpp
[28] Web search · Ollama Blog https://ollama.com/blog/web-search
[29] Tool calling - Ollama's documentation https://docs.ollama.com/capabilities/tool-calling
[30] Ollama Function Calling with Search API - GitHub https://github.com/srbhr/Ollama-function-calling
[31] Built a simple way to one-click install and connect MCP servers to ... https://www.reddit.com/r/ollama/comments/1kiw05t/built_a_simple_way_to_oneclick_install_and/
[32] Set Up ClickHouse MCP Server with Ollama https://clickhouse.com/docs/use-cases/AI/MCP/ollama
[33] AI Agent Usage - AnythingLLM Docs https://docs.useanything.com/agent/usage
[34] AnythingLLM - Documentation - Novita AI https://novita.ai/docs/guides/anythingllm
[35] AI Agent Setup - AnythingLLM Docs https://docs.useanything.com/agent/setup
[36] AnythingLLM Review (2025): Local AI, RAG, Agents & Setup Guide https://skywork.ai/blog/anythingllm-review-2025-local-ai-rag-agents-setup/
[37] OpenWebUI with Searxng and DeepSeek R1 Integration - GitHub https://github.com/NovagridAI/Open-webui-SearxNG-Function
[38] Searxng Integration with Open Webui - YouTube https://www.youtube.com/watch?v=vRc7PTdffro
[39] SearXNG - Open WebUI https://docs.openwebui.com/tutorials/web-search/searxng/
[40] OpenWebUI has an option for a SearXNG API key - Cloudron Forum https://forum.cloudron.io/topic/12201/openwebui-has-an-option-for-a-searxng-api-key
[41] Error while enabling the Searxng as web search engine in Open ... https://stackoverflow.com/questions/79043814/error-while-enabling-the-searxng-as-web-search-engine-in-open-web-ui
[42] Unlimited Search API for AI Agents – 100% FREE with n8n! (Full ... https://www.youtube.com/watch?v=O5b9FvHYjqc
[43] MCP vs. Function Calling: How They Differ and Which to Use https://www.descope.com/blog/post/mcp-vs-function-calling
[44] The Complete Guide to Web Search APIs for AI Applications in 2025 https://www.firecrawl.dev/blog/top_web_search_api_2025
[45] Which search API should I use between Tavily.com, Exa.ai and ... https://www.reddit.com/r/Rag/comments/1gr8jnr/which_search_api_should_i_use_between_tavilycom/
[46] Web Search with Llama.cpp? : r/LocalLLaMA - Reddit https://www.reddit.com/r/LocalLLaMA/comments/1ioo19z/web_search_with_llamacpp/
[47] vatsalsaglani/llama-cpp-search - GitHub https://github.com/vatsalsaglani/llama-cpp-search
[48] How to add Brave Search to Claude Desktop with MCP https://brave.com/search/api/guides/use-with-claude-desktop-with-mcp/
[49] How to Set Up MCP Servers Locally Using Docker https://www.mcpevals.io/blog/setup-local-mcp-servers-with-docker
[50] Run MCP Servers In Seconds With Docker - DEV Community https://dev.to/pradumnasaraf/run-mcp-servers-in-seconds-with-docker-1ik5
[51] 使用 Docker 设置 MCP 服务器 | MCP Servers - LobeHub https://lobehub.com/mcp/yugp31-mcp-server-docker-guide
[52] MCP meets Ollama: Build a 100% local MCP client - YouTube https://www.youtube.com/watch?v=C64rVY1eN8k
[53] The 6 Best LLM Tools To Run Models Locally - GetStream.io https://getstream.io/blog/best-local-llm-tools/
[54] Has anybody successfully implemented web search/browsing for ... https://www.reddit.com/r/LocalLLaMA/comments/180jz0x/has_anybody_successfully_implemented_web/
[55] Is there a list of all usable AI models that can run selfhosted offline https://www.reddit.com/r/selfhosted/comments/15hk9d2/is_there_a_list_of_all_usable_ai_models_that_can/
[56] Browser Automation MCP Servers Guide October 2025 - Skyvern https://www.skyvern.com/blog/browser-automation-mcp-servers-guide/
[57] How LLMs access real-time data from the web - ML6 https://www.ml6.eu/en/blog/how-llms-access-real-time-data-from-the-web
[58] Top 8 Local LLM Tools: Run AI Models Offline and Keep Your Data ... https://www.aifire.co/p/top-8-local-llm-tools-run-ai-models-offline-and-keep-your-data-safe
[59] MCP Tools Usage Guide - Scott Spence https://scottspence.com/posts/efficient-mcp-tools-usage-guide
[60] Prat011/awesome-llm-skills - GitHub https://github.com/Prat011/awesome-llm-skills
[61] Top 10 open source LLMs for 2025 - Instaclustr https://www.instaclustr.com/education/open-source-ai/top-10-open-source-llms-for-2025/
[62] Characterizing Web Search in The Age of Generative AI - arXiv https://arxiv.org/html/2510.11560v1
[63] The Best Self-Hosted AI Tools You Can Actually Run in ... - YouTube https://www.youtube.com/watch?v=illvibK_ZmY
[64] Tools - Model Context Protocol https://modelcontextprotocol.io/specification/2025-06-18/server/tools
[65] Free LLM Desktop Tools - The Ultimate Comparison for 2025 https://sailingbyte.com/blog/the-ultimate-comparison-of-free-desktop-tools-for-running-local-llms/
[66] The best web search for your AI | Parallel https://parallel.ai/products/search
[67] Does any API model have web search? https://community.openai.com/t/does-any-api-model-have-web-search/1114071
[68] MCP Server Finder Directory | The Ultimate Model Context Protocol ... https://www.mcpserverfinder.com
[69] Open Protocols for Agent Interoperability Part 3 - Amazon AWS https://aws.amazon.com/blogs/opensource/open-protocols-for-agent-interoperability-part-3-strands-agents-mcp/
[70] Self-host LLMs in production with llama.cpp llama-server https://docs.servicestack.net/ai-server/llama-server
[71] Best Web Search MCP? : r/modelcontextprotocol - Reddit https://www.reddit.com/r/modelcontextprotocol/comments/1kjoxsy/best_web_search_mcp/
[72] Bootstrap Your Own Skills: Learning to Solve New Tasks with LLM ... https://clvrai.github.io/boss/
[73] How to Host and Run LLMs Locally with Ollama & llama.cpp https://www.youtube.com/watch?v=AHlx91CKmmc
[74] Awesome MCP Servers https://mcpservers.org
[75] Capability-Driven Skill Generation with LLMs: A RAG-Based ... - arXiv https://arxiv.org/html/2505.03295v1
[76] guide : using the new WebUI of llama.cpp #16938 - GitHub https://github.com/ggml-org/llama.cpp/discussions/16938
[77] MCP Server Directory: 6490+ updated daily - PulseMCP https://www.pulsemcp.com/servers
[78] What Are LLM Agents and How To Implement Them in 2025 - Turing https://www.turing.com/resources/what-are-llm-agents-and-how-to-implement
[79] Lightweight chat web UI that supports on-disk storage and can hook ... https://www.reddit.com/r/LocalLLaMA/comments/1nijl9n/lightweight_chat_web_ui_that_supports_ondisk/
[80] punkpeye/awesome-mcp-servers - GitHub https://github.com/punkpeye/awesome-mcp-servers
[81] LLM Agents - Prompt Engineering Guide https://www.promptingguide.ai/research/llm-agents
[82] ggml-org/llama.cpp: LLM inference in C/C++ - GitHub https://github.com/ggml-org/llama.cpp
[83] Browse All MCP Servers - MCP Market https://mcpmarket.com/server
[84] How to Implement LLM Workflows with the Model Context Protocol ... https://www.reddit.com/r/Anthropic/comments/1j4mp3a/building_intelligent_agents_how_to_implement_llm/
[85] llama.cpp guide - Running LLMs locally, on any hardware, from ... https://steelph0enix.github.io/posts/llama-cpp-guide/
[86] MCP Servers https://mcp.so
[87] A Visual Guide to LLM Agents - by Maarten Grootendorst https://newsletter.maartengrootendorst.com/p/a-visual-guide-to-llm-agents
[88] Brave Search MCP server for AI agents - Playbooks https://playbooks.com/mcp/modelcontextprotocol-brave-search
[89] MCP-SearXNG-Enhanced Web Search https://mcpservers.org/servers/OvertliDS/mcp-searxng-enhanced
[90] Tavily MCP Server https://docs.tavily.com/documentation/mcp
[91] Tavily - The Web Access Layer for AI Agents https://tavily.com
[92] mcp/brave-search - Docker Image - Docker Hub https://hub.docker.com/r/mcp/brave-search
[93] Tools - OpenAI Agents SDK https://openai.github.io/openai-agents-python/tools/
[94] Function Calling with LLMs - Prompt Engineering Guide https://www.promptingguide.ai/applications/function_calling
[95] How to Use llama.cpp to Run LLaMA Models Locally - Codecademy https://www.codecademy.com/article/llama-cpp
[96] Function calling using LLMs - Martin Fowler https://martinfowler.com/articles/function-call-LLM.html
[97] I've made an "ultimate" guide about building and using `llama.cpp` https://www.reddit.com/r/LocalLLaMA/comments/1h2hioi/ive_made_an_ultimate_guide_about_building_and/
[98] Fully local tool calling with Ollama - YouTube https://www.youtube.com/watch?v=Nfk99Fz8H9k
[99] Most capable function calling open source models? : r/LocalLLaMA https://www.reddit.com/r/LocalLLaMA/comments/1ackxxt/most_capable_function_calling_open_source_models/
[100] Ollama tool calling | IBM https://www.ibm.com/think/tutorials/local-tool-calling-ollama-granite
[101] rizerphe/local-llm-function-calling - GitHub https://github.com/rizerphe/local-llm-function-calling
[102] Locally hosted LLM is not able to call tools - n8n Community https://community.n8n.io/t/locally-hosted-llm-is-not-able-to-call-tools/138631
[103] Llama.cpp and Ollama servers + plugins for VS Code / VS Codium ... https://discuss.linuxcontainers.org/t/llama-cpp-and-ollama-servers-plugins-for-vs-code-vs-codium-and-intellij-ai/19744
[104] llama.server: is it possible to add search engine binding with LLAM ... https://github.com/ggerganov/llama.cpp/discussions/11810
[105] Ollama MCP Server | Glama https://glama.ai/mcp/servers/@NightTrek/Ollama-mcp
[106] rawveg/ollama-mcp: An MCP Server for Ollama - GitHub https://github.com/rawveg/ollama-mcp
[107] Function Calling Comparison: MCP vs OpenAI https://mcpmarket.com/server/function-calling-comparison
[108] How to Use MCP with Ollama (without Claude, with Dolphin MCP) https://apidog.com/blog/mcp-ollama/
[109] Trying out llama.cpp's new vision support - Simon Willison's Newsletter https://simonw.substack.com/p/trying-out-llamacpps-new-vision-support
[110] Model Context Protocol vs Function Calling: What's the Big Difference? https://www.reddit.com/r/ClaudeAI/comments/1h0w1z6/model_context_protocol_vs_function_calling_whats/
[111] The Great AI Agent Protocol Race: Function Calling vs. MCP vs. A2A https://zilliz.com/blog/function-calling-vs-mcp-vs-a2a-developers-guide-to-ai-agent-protocols
[112] Starting with Llama.cpp - Open WebUI https://docs.openwebui.com/getting-started/quick-start/starting-with-llama-cpp/
[113] Connect Local AI Agent (Ollama) to Tools with MCP Server and Client https://www.youtube.com/watch?v=aiH79Q-LGjY
[114] A surprising discovery me! About MCP and Function calling https://community.openai.com/t/a-surprising-discovery-me-about-mcp-and-function-calling/1223345
[115] Self-hosted MCP Gateway and Registry for AI agents - GitHub https://github.com/mcpjungle/MCPJungle
[116] Configuration - AnythingLLM Docs https://docs.anythingllm.com/configuration
[117] Self-hosted MCP server generation | Speakeasy https://www.speakeasy.com/product/mcp-server
[118] AnythingLLM Browser Extension https://docs.anythingllm.com/browser-extension/install
[119] Docker Just Made Using MCP Servers 100x Easier (One ... - YouTube https://www.youtube.com/watch?v=TxlVdB2gmGE
[120] Unlimited private web-scraping for AI Agents | AnythingLLM - YouTube https://www.youtube.com/watch?v=Ik_A5jXPK-A
[121] SearXNG -> Open webUI integration not working. HELP! - Reddit https://www.reddit.com/r/Searx/comments/1ed34ml/searxng_open_webui_integration_not_working_help/
[122] How to build and deliver an MCP server for production - Docker https://www.docker.com/blog/build-to-prod-mcp-servers-with-docker/
[123] trying to get AnythingLLM's web agent skills working in 24.10 - Reddit https://www.reddit.com/r/truenas/comments/1o42odv/trying_to_get_anythingllms_web_agent_skills/
[124] Are Ollama and Open WebUI the best self-hosted alternatives for ... https://www.reddit.com/r/selfhosted/comments/1ioqkjm/are_ollama_and_open_webui_the_best_selfhosted/
[125] Best 30+ Open Source Web Agents - Research AIMultiple https://research.aimultiple.com/open-source-web-agents/
[126] Web Search API for LLMs & AI Agents - WebSearchAPI.ai https://websearchapi.ai
[127] Top Open WebUI Alternatives for Running LLMs Locally - Helicone https://www.helicone.ai/blog/open-webui-alternatives
[128] Cheapest Realtime Web Search AI API? : r/AI_Agents - Reddit https://www.reddit.com/r/AI_Agents/comments/1jl653q/cheapest_realtime_web_search_ai_api/
[129] 6 Self-Hosted & Local LLMs - Budibase https://budibase.com/blog/ai-agents/local-llms/
[130] Top 5 Anthropic Web Search Alternatives of 2025 - Scrapeless https://www.scrapeless.com/en/blog/anthropic-web-search-alternatives
[131] Exa | Web Search API, AI Search Engine, & Website Crawler https://exa.ai
[132] Firecrawl - The Web Data API for AI https://www.firecrawl.dev
[133] The 11 best open-source LLMs for 2025 - n8n Blog https://blog.n8n.io/open-source-llm/
[134] Beyond Exa: Exploring Neural Search and Semantic Search ... https://scrapegraphai.com/blog/exa-alternatives
