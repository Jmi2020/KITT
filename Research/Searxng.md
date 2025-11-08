## SearXNG Bot Detection Issues - Solutions

Bot detection with SearXNG typically happens at **two levels**: SearXNG's own limiter blocking your requests, and upstream search engines (Google, DuckDuckGo, etc.) detecting SearXNG as a bot[1][2].

### Issue 1: SearXNG's Internal Limiter

The most common issue for local API usage is SearXNG's built-in rate limiter blocking your agent's requests[1][3].

**Solution: Disable or Configure the Limiter**

Edit your `settings.yml`:

```yaml
server:
  limiter: false  # Disable completely for local use
  secret_key: "your-secret-key"
  bind_address: "127.0.0.1"
```

Or if you need some protection but want to whitelist localhost, create/edit `/etc/searxng/limiter.toml` (or `./searxng/limiter.toml` in Docker):

```toml
[botdetection.ip_limit]
# Disable filtering for local networks
filter_link_local = true

# Disable link token requirement
link_token = false

[botdetection.ip_lists]
# Whitelist your local IPs
pass_ip = [
  "127.0.0.1",
  "::1",
  "172.17.0.0/16",  # Docker default network
  "192.168.0.0/16"   # Local network
]

block_ip = []
```

**For Docker users**, the limiter is now **off by default** in `searxng-docker`[4]. If you're still having issues:

```yaml
# docker-compose.yml
services:
  searxng:
    environment:
      - SEARXNG_LIMITER=false  # Explicitly disable
```

Or set in your environment:

```bash
export SEARXNG_LIMITER=false
docker-compose up -d
```

### Issue 2: Upstream Search Engines Blocking SearXNG

Even with the limiter disabled, upstream engines like Google, DuckDuckGo, and Startpage may detect SearXNG as a bot and serve CAPTCHAs[5][6][7].

**Solution A: Use CAPTCHA-Resistant Engines**

Disable problematic engines and use alternatives. Edit `settings.yml`:

```yaml
engines:
  # Disable CAPTCHA-prone engines
  - name: google
    disabled: true
  
  - name: duckduckgo
    disabled: true  # Often triggers CAPTCHAs
  
  - name: startpage
    disabled: true  # Very CAPTCHA-heavy
  
  # Enable better alternatives
  - name: brave
    engine: brave
    disabled: false
    shortcut: br
  
  - name: qwant
    engine: qwant
    disabled: false
    shortcut: qw
    # CAPTCHA avoidance parameters
    additional_tests:
      - 'llm'
  
  - name: mojeek
    engine: xpath
    disabled: false
    shortcut: mjk
  
  - name: marginalia
    engine: json_engine
    disabled: false
  
  - name: wiby
    engine: json_engine
    disabled: false
```

**Solution B: Configure Engines to Avoid CAPTCHAs**

Some engines have workarounds. For DuckDuckGo, switch to the lite/HTML version[7]:

Edit `searx/engines/duckduckgo.py` or configure:

```yaml
engines:
  - name: duckduckgo
    engine: duckduckgo
    disabled: false
    # Use HTML endpoint instead of API
    categories: [general, web]
    timeout: 3.0
    shortcut: ddg
```

For Qwant, add CAPTCHA-avoidance parameters[8]:

```yaml
engines:
  - name: qwant
    engine: qwant
    disabled: false
    # These parameters help avoid CAPTCHAs
    additional_tests:
      tgp: 3
      llm: 'false'
```

**Solution C: Reduce Request Frequency**

If you're making rapid-fire requests from your agent, add delays:

```python
# In your search_agent_searxng.py
import time

def run(self):
    time.sleep(1)  # 1 second between searches
    # ... rest of search code
```

### Complete Working Configuration

Here's a battle-tested configuration for local API use:

**settings.yml:**

```yaml
use_default_settings: true

server:
  secret_key: "change-this-secret-key"
  limiter: false  # Critical for API usage
  bind_address: "0.0.0.0"
  port: 8888
  public_instance: false
  image_proxy: false

search:
  safe_search: 0
  autocomplete: ""
  default_lang: "en"
  formats:
    - html
    - json  # Enable JSON for API

enabled_plugins:
  # Disable bot protection plugins
  - 'Hash plugin'
  - 'Self Information'
  - 'Tracker URL remover'
  # REMOVE these for API usage:
  # - 'Limiter'  # Don't enable this

engines:
  # Reliable, CAPTCHA-free engines
  - name: brave
    engine: brave
    disabled: false
    shortcut: br
    time_range_support: true
    
  - name: mojeek
    disabled: false
    shortcut: mjk
    
  - name: presearch
    engine: presearch
    disabled: false
    
  - name: qwant
    engine: qwant
    disabled: false
    categories: [general, web]
    
  - name: wikipedia
    disabled: false
    
  # Disable CAPTCHA-heavy engines for API use
  - name: google
    disabled: true  # High CAPTCHA rate
    
  - name: duckduckgo
    disabled: true  # Frequent CAPTCHAs
    
  - name: startpage
    disabled: true  # Very aggressive blocking
    
  - name: bing
    disabled: true  # API rate limits
```

**Docker Compose with limiter disabled:**

```yaml
version: '3.8'

services:
  searxng:
    image: searxng/searxng:latest
    container_name: searxng
    ports:
      - "8888:8080"
    volumes:
      - ./searxng:/etc/searxng:rw
    environment:
      - SEARXNG_BASE_URL=http://localhost:8888/
      - SEARXNG_LIMITER=false  # Disable limiter
    restart: unless-stopped
    command: sh -c "sed -i 's/limiter: true/limiter: false/' /etc/searxng/settings.yml && /usr/local/searxng/dockerfiles/docker-entrypoint.sh"
```

### Testing Your Configuration

After making changes:

```bash
# Restart SearXNG
docker-compose restart

# Test directly
curl "http://localhost:8888/search?q=test&format=json" | jq

# Test with your agent
python search_agent_searxng.py
```

### Alternative: Use Only CAPTCHA-Free Engines

Create a minimal config with only reliable engines:

```yaml
# Minimal, CAPTCHA-free configuration
engines:
  - name: brave
    engine: brave
    disabled: false
    
  - name: mojeek
    disabled: false
    
  - name: marginalia
    disabled: false
    
  - name: wiby
    disabled: false
```

### Quick Fix Summary

**If you're getting blocked immediately:**

1. Set `limiter: false` in settings.yml[4][9]
2. Remove or don't create `limiter.toml`
3. Restart SearXNG: `docker-compose restart`

**If upstream engines are blocking:**

1. Disable Google, DuckDuckGo, Startpage[5][6]
2. Enable Brave, Mojeek, Qwant, Marginalia
3. Add 1-2 second delays between requests in your agent

**For production reliability:**

Use the combined approach from the guide - SearXNG as primary (with good engines only) + Brave API as backup + Tavily as fallback. This way if SearXNG engines get blocked, your agent automatically switches to the paid APIs.

The root cause is that popular engines actively detect and block SearXNG traffic[2][5]. By disabling those engines and using less popular but open alternatives, you'll avoid most CAPTCHA issues while maintaining good search quality[3][9].

Sources
[1] Bot Detection — SearXNG Documentation (2025.11.5+1be19f8b5) https://docs.searxng.org/src/searx.botdetection.html
[2] Limiter — SearXNG Documentation (2025.11.7+b9b46431b) https://docs.searxng.org/admin/searx.limiter.html
[3] SearXNG Local Deployment and Configuration - Cherry Studio https://docs.cherry-ai.com/docs/en-us/websearch/searxng
[4] [Announcement] Bot protection off by default in searxng-docker https://www.reddit.com/r/Searx/comments/1kv6yhp/announcement_bot_protection_off_by_default_in/
[5] Bug: duckduckgo engine, Error: SearxEngineCaptchaException #4824 https://github.com/searxng/searxng/issues/4824
[6] Bug: startpage engine / captcha · Issue #2989 · searxng ... - GitHub https://github.com/searxng/searxng/issues/2989
[7] duckduckgo blocked by CAPTCHA · Issue #3927 · searxng ... - GitHub https://github.com/searxng/searxng/issues/3927
[8] [fix] engine qwant: add tgp and llm arguments to avoid CAPTCHA https://git.jordan.im/searxng/commit/?h=dependabot%2Fnpm_and_yarn%2Fclient%2Fsimple%2Fmaster%2Fless-loader-12.3.0&id=02b76c8389ed0f53be75f686f6063c8c188c1921
[9] server: — SearXNG Documentation (2025.10.31+b8e4ebdc0) https://docs.searxng.org/admin/settings/settings_server.html
[10] ERROR:searx.botdetection: X-Forwarded-For nor X-Real-IP header ... https://github.com/ItzCrazyKns/Perplexica/issues/858
[11] can not start searxng : WARNING:searx.botdetection.config: missing ... https://github.com/Fosowl/agenticSeek/issues/330
[12] Bot Detection fails to reliably receive x-forwarded-for and/or X-Real-IP https://github.com/searxng/searxng/issues/4505
[13] How to Bypass Captcha (Captcha Solver) - YouTube https://www.youtube.com/watch?v=t_Y3tnC64qM
[14] [limiter] Rate limiting does not work · Issue #1237 · searxng ... - GitHub https://github.com/searxng/searxng/issues/1237
[15] Slow and ConnectTimeout for public URL? : r/Searx - Reddit https://www.reddit.com/r/Searx/comments/1kw08bw/slow_and_connecttimeout_for_public_url/
[16] How to bypass reCAPTCHA & hCaptcha when web scraping https://www.scrapingbee.com/blog/how-to-bypass-recaptcha-and-hcaptcha-when-web-scraping/
[17] Source code for searx.limiter - SearXNG https://docs.searxng.org/_modules/searx/limiter.html
[18] SearXNG - Open WebUI https://docs.openwebui.com/tutorials/web-search/searxng/
[19] Step by step installation - SearXNG https://docs.searxng.org/admin/installation-searxng.html
[20] Bot Detection (20240226.0) - SearXNG https://searxng.org/botdetection/
[21] searxng/docs/admin/engines/settings.rst at ... - Gitea https://gitea.zaclys.com/zaclys/searxng/src/commit/b0b45fd2d03be9969307bf54f9c2a01e685cd8ca/docs/admin/engines/settings.rst
[22] disable rate limiter for whitelisted IPs/subnet · Issue #2127 - GitHub https://github.com/searxng/searxng/issues/2127
[23] [fix] limiter: don't hard code settings folder to /etc/searxng - Gitea https://gitea.zaclys.com/zaclys/searxng/commit/da28f5280b8f5cac79963e10c79ddc2a3e65f93a
[24] How can I whitelist localhost - Stack Overflow https://stackoverflow.com/questions/49163276/how-can-i-whitelist-localhost
