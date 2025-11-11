
# 🐱 KITTY — Network Discovery on macOS (Docker Desktop)

> Discover Bambu (mDNS), Snapmaker (SSDP/UDP 20054), and general devices (ICMP ping) from a container. Runs on a Mac Studio (Apple Silicon) using Docker Compose, updates Redis for orchestration, and emits events when devices appear or change state.

## Table of contents
- [Why this design](#why-this-design)
- [Architecture](#architecture)
- [Prereqs](#prereqs)
- [Directory layout](#directory-layout)
- [Environment](#environment)
- [Python service (complete code)](#python-service-complete-code)
- [Dockerfile](#dockerfile)
- [Docker Compose](#docker-compose)
- [Build & run](#build--run)
- [Verification](#verification)
- [Integration ideas](#integration-ideas)
- [macOS notes & options](#macos-notes--options)
- [Troubleshooting](#troubleshooting)
- [See also](#see-also)
- [You may also enjoy](#you-may-also-enjoy)

---

## Why this design

- mDNS/Bonjour (multicast UDP 5353) is how many devices self-advertise (e.g., Bambu HTTP/IPP services). Learn more: 🔎 [mDNS / Zeroconf](https://www.google.com/search?q=mdns+zeroconf+bonjour+how+it+works)
- SSDP (multicast UDP 1900) is used by UPnP devices; **Snapmaker** also exposes an ultra-light discovery on **UDP 20054** using a broadcast "discover" message. 📡 [SSDP 239.255.255.250:1900](https://www.google.com/search?q=SSDP+239.255.255.250+1900+protocol) • 🧪 [Snapmaker UDP 20054](https://www.google.com/search?q=Snapmaker+Luban+UDP+20054+discover)
- Ping sweeps catch "quiet" devices (e.g., Raspberry Pi without service adverts). ⚡️ [icmplib (Python ping)](https://www.google.com/search?q=icmplib+python+ping)
- **macOS caveat:** Docker Desktop does **not** offer true `--network=host` and limits multicast from containers. We lean on **active** queries (SSDP/Snapmaker broadcast + pings). For richer mDNS, see options below. 🍎 [Docker Desktop host networking macOS](https://www.google.com/search?q=Docker+Desktop+Mac+host+networking+multicast+not+supported)

---

## Architecture

```
+-------------------------------+
| Mac Studio (Docker Desktop)   |
|                               |
|  docker compose               |
|  ┌─────────────────────────┐  |    UDP 1900 SSDP  ◀───── LAN devices
|  │ discovery (Python)      │  |    UDP 20054 broadcast ◀─ Snapmaker
|  │  • mDNS (best-effort)   │  |    UDP 5353 mDNS   ◀──── (limited on macOS)
|  │  • SSDP + Snapmaker     │  |    ICMP ping       ◀──── All devices
|  │  • ICMP ping sweep      │  |
|  │  • Redis registry       │  |
|  │  • Pub/Sub events       │  |
|  └─────────────────────────┘  |
|             │                  |
|         TCP │                  |
|             ▼                  |
|        Redis:6379              |
+-------------------------------+
```

- The discovery service runs loops every N seconds, updates Redis keys `device:*`, and publishes events on `events:*` channels.
- KITTY orchestration can **poll** or **subscribe** to react when printers appear or become idle.

---

## Prereqs

- macOS 14+ on Apple Silicon (M3 OK)
- Docker Desktop (Apple Silicon)
- Git + Make (optional)
- Network: know your home LAN CIDR (e.g., `192.168.1.0/24`)
- (Optional) Redis already in your KITTY stack; otherwise Compose below provides one.

---

## Directory layout

Create a new folder (or drop into your KITTY repo). Example:

```
services/
  discovery/
    Dockerfile
    requirements.txt
    app.py
docker-compose.discovery.yml
.env.discovery
```

---

## Environment

Create **`.env.discovery`** at the project root (edit subnets to match your LAN; multiple subnets comma-separated):

```dotenv
# Redis connection (compose service name or host:port)
REDIS_URL=redis://redis:6379/0

# Comma-separated IPv4 CIDRs to scan (home LANs)
DISCOVERY_SUBNETS=192.168.1.0/24

# Enable/disable modules
ENABLE_MDNS=1
ENABLE_SSDP=1
ENABLE_SNAPMAKER=1
ENABLE_PING=1

# Intervals (seconds)
SCAN_LOOP_INTERVAL=60            # base loop (mDNS/SSDP/Snapmaker)
PING_SWEEP_INTERVAL=300          # full ICMP sweep (e.g., every 5 min)

# SSDP tuning
SSDP_MX=1
SSDP_TIMEOUT=2

# Snapmaker discovery
SNAPMAKER_PORT=20054
SNAPMAKER_TIMEOUT=2

# HTTP API (optional read-only endpoints)
API_PORT=8088

# Device TTL (seconds) before considered stale
DEVICE_TTL=900
```

---

## Python service (complete code)

> Single-file service: async loops for mDNS, SSDP, Snapmaker, and ping; Redis-backed registry; minimal FastAPI for status/inspection.

**`services/discovery/app.py`**
```python
import asyncio
import ipaddress
import json
import logging
import os
import socket
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from fastapi import FastAPI
from redis.asyncio import Redis

# mDNS / Zeroconf (best-effort on macOS Docker)
try:
    from zeroconf.asyncio import AsyncZeroconf, AsyncServiceBrowser
    from zeroconf import ServiceStateChange
    ZEROCONF_AVAILABLE = True
except Exception:
    ZEROCONF_AVAILABLE = False

# ICMP ping
from icmplib import multiping, Host

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
SUBNETS = [s.strip() for s in os.getenv("DISCOVERY_SUBNETS", "192.168.1.0/24").split(",") if s.strip()]

ENABLE_MDNS = os.getenv("ENABLE_MDNS", "1") == "1"
ENABLE_SSDP = os.getenv("ENABLE_SSDP", "1") == "1"
ENABLE_SNAPMAKER = os.getenv("ENABLE_SNAPMAKER", "1") == "1"
ENABLE_PING = os.getenv("ENABLE_PING", "1") == "1"

SCAN_LOOP_INTERVAL = int(os.getenv("SCAN_LOOP_INTERVAL", "60"))
PING_SWEEP_INTERVAL = int(os.getenv("PING_SWEEP_INTERVAL", "300"))

SSDP_MX = int(os.getenv("SSDP_MX", "1"))
SSDP_TIMEOUT = float(os.getenv("SSDP_TIMEOUT", "2"))
SNAPMAKER_PORT = int(os.getenv("SNAPMAKER_PORT", "20054"))
SNAPMAKER_TIMEOUT = float(os.getenv("SNAPMAKER_TIMEOUT", "2"))

API_PORT = int(os.getenv("API_PORT", "8088"))
DEVICE_TTL = int(os.getenv("DEVICE_TTL", "900"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("discovery")

# ----------------------------------------------------------------------------
# Device model + registry
# ----------------------------------------------------------------------------

@dataclass
class Device:
    id: str
    ip: str
    name: str = ""
    kind: str = ""        # e.g., 'bambu', 'snapmaker', 'printer', 'host'
    status: str = ""      # e.g., 'IDLE', 'RUNNING', 'online'
    source: str = ""      # 'mdns', 'ssdp', 'snapmaker', 'ping'
    last_seen: float = 0  # epoch seconds

    def key(self) -> str:
        return f"device:{self.id}"

class Registry:
    def __init__(self, redis: Redis):
        self.r = redis

    async def upsert(self, d: Device) -> None:
        d.last_seen = time.time()
        mapping = asdict(d)
        # store as Redis hash
        await self.r.hset(d.key(), mapping=mapping)
        await self.r.sadd("devices:all", d.key())
        # TTL so stale devices expire from keys; also keep in set separately
        await self.r.expire(d.key(), DEVICE_TTL)

    async def get_all(self) -> List[Dict]:
        keys = await self.r.smembers("devices:all")
        out = []
        for k in keys:
            fields = await self.r.hgetall(k)
            if fields:
                # convert bytes to str for readability
                out.append({(kk.decode() if isinstance(kk, bytes) else kk): (vv.decode() if isinstance(vv, bytes) else vv) for kk, vv in fields.items()})
        return out

    async def publish(self, channel: str, payload: Dict) -> None:
        await self.r.publish(channel, json.dumps(payload))

# ----------------------------------------------------------------------------
# mDNS (Bonjour) discovery (best-effort)
# ----------------------------------------------------------------------------

MDNS_SERVICE_TYPES = [
    "_http._tcp.local.",
    "_ipp._tcp.local.",
    "_printer._tcp.local.",
    "_octoprint._tcp.local.",
]

def classify_mdns(name: str) -> Tuple[str, str]:
    n = name.lower()
    if any(x in n for x in ["bambu", "x1", "p1p", "a1"]):
        return ("bambu", "online")
    if "octoprint" in n or "klipper" in n or "printer" in n:
        return ("printer", "online")
    return ("host", "online")

async def mdns_discover(reg: Registry) -> None:
    if not ZEROCONF_AVAILABLE:
        log.debug("zeroconf not available, skipping mDNS scan")
        return
    try:
        azc = AsyncZeroconf()
        results: List[Tuple[str, str, str, int]] = []  # (name, ip, svc, port)

        loop = asyncio.get_event_loop()
        done_event = asyncio.Event()

        def on_service_update(zeroconf, service_type, name, state_change):
            # We handle only added/updated
            if state_change in (ServiceStateChange.Added, ServiceStateChange.Updated):
                info = zeroconf.get_service_info(service_type, name)
                if info and info.addresses:
                    ip = socket.inet_ntoa(info.addresses[0])
                    results.append((name, ip, service_type, info.port))

        # Start browsers for each service type
        browsers = [AsyncServiceBrowser(azc.zeroconf, st, handlers=[on_service_update]) for st in MDNS_SERVICE_TYPES]

        # Let it run for a short window
        await asyncio.sleep(3.0)

        # Process results
        for (name, ip, svc, port) in results:
            kind, status = classify_mdns(name)
            dev_id = f"{kind}:{ip}"
            d = Device(id=dev_id, ip=ip, name=name, kind=kind, status=status, source="mdns")
            await reg.upsert(d)

        await azc.async_close()
    except Exception as e:
        log.debug(f"mDNS scan error: {e}")

# ----------------------------------------------------------------------------
# SSDP discovery (UPnP)
# ----------------------------------------------------------------------------

def ssdp_msearch(st: str = "ssdp:all", mx: int = SSDP_MX, timeout: float = SSDP_TIMEOUT) -> List[Tuple[str, str]]:
    msg = "\r\n".join([
        'M-SEARCH * HTTP/1.1',
        'HOST: 239.255.255.250:1900',
        'MAN: "ssdp:discover"',
        f'MX: {mx}',
        f'ST: {st}',
        '', ''
    ]).encode("utf-8")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    try:
        sock.sendto(msg, ("239.255.255.250", 1900))
        responses = []
        while True:
            try:
                data, addr = sock.recvfrom(8192)
                responses.append((addr[0], data.decode("utf-8", errors="ignore")))
            except socket.timeout:
                break
        return responses
    finally:
        sock.close()

async def ssdp_discover(reg: Registry) -> None:
    try:
        resps = await asyncio.get_event_loop().run_in_executor(None, ssdp_msearch)
        for (ip, payload) in resps:
            # Minimal parse; treat as generic SSDP device
            dev_id = f"ssdp:{ip}"
            d = Device(id=dev_id, ip=ip, name="", kind="device", status="online", source="ssdp")
            await reg.upsert(d)
    except Exception as e:
        log.debug(f"SSDP scan error: {e}")

# ----------------------------------------------------------------------------
# Snapmaker discovery (UDP broadcast: 20054, payload 'discover')
# ----------------------------------------------------------------------------

def snapmaker_probe(port: int = SNAPMAKER_PORT, timeout: float = SNAPMAKER_TIMEOUT) -> List[Tuple[str, str]]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.sendto(b"discover", ("255.255.255.255", port))
        results = []
        while True:
            try:
                data, addr = sock.recvfrom(2048)
                results.append((addr[0], data.decode("utf-8", errors="ignore").strip()))
            except socket.timeout:
                break
        return results
    finally:
        sock.close()

async def snapmaker_discover(reg: Registry) -> None:
    try:
        resps = await asyncio.get_event_loop().run_in_executor(None, snapmaker_probe)
        for (ip, payload) in resps:
            name = ""
            status = ""
            kind = "snapmaker"
            # Payload is JSON-like; attempt to parse fields if present
            try:
                obj = json.loads(payload)
                name = obj.get("model") or obj.get("name") or ""
                status = obj.get("state") or obj.get("status") or "online"
            except Exception:
                status = "online"
            dev_id = f"{kind}:{ip}"
            d = Device(id=dev_id, ip=ip, name=name, kind=kind, status=status, source="snapmaker")
            await reg.upsert(d)
            # Example: publish idle transitions
            if status.upper() == "IDLE":
                await reg.publish("events:printer_idle", {"id": dev_id, "ip": ip, "name": name})
    except Exception as e:
        log.debug(f"Snapmaker scan error: {e}")

# ----------------------------------------------------------------------------
# ICMP ping sweep
# ----------------------------------------------------------------------------

def expand_hosts(subnets: List[str]) -> List[str]:
    hosts = []
    for cidr in subnets:
        try:
            net = ipaddress.ip_network(cidr, strict=False)
            hosts.extend([str(h) for h in net.hosts()])
        except Exception:
            pass
    return hosts

async def ping_sweep(reg: Registry) -> None:
    targets = expand_hosts(SUBNETS)
    if not targets:
        return
    try:
        # multiping returns Host objects; privileged raw ICMP suggested
        alive: List[Host] = multiping(targets, count=1, interval=0, timeout=1, privileged=True)
        for host in alive:
            if host.is_alive:
                ip = host.address
                dev_id = f"host:{ip}"
                d = Device(id=dev_id, ip=ip, name="", kind="host", status="online", source="ping")
                await reg.upsert(d)
    except Exception as e:
        log.debug(f"Ping sweep error: {e}")

# ----------------------------------------------------------------------------
# App + loops
# ----------------------------------------------------------------------------

app = FastAPI(title="KITTY Discovery", version="1.0.0")
redis_client: Optional[Redis] = None
registry: Optional[Registry] = None

@app.on_event("startup")
async def on_startup():
    global redis_client, registry
    redis_client = Redis.from_url(REDIS_URL, decode_responses=False)
    registry = Registry(redis_client)
    asyncio.create_task(main_loop())

@app.on_event("shutdown")
async def on_shutdown():
    if redis_client:
        await redis_client.aclose()

@app.get("/health")
async def health():
    return {"status": "ok", "mdns": ENABLE_MDNS, "ssdp": ENABLE_SSDP, "snapmaker": ENABLE_SNAPMAKER, "ping": ENABLE_PING}

@app.get("/devices")
async def devices():
    return await registry.get_all() if registry else []

last_ping_run = 0.0

async def main_loop():
    global last_ping_run
    while True:
        try:
            if registry is None:
                await asyncio.sleep(1)
                continue

            tasks = []
            if ENABLE_MDNS:
                tasks.append(mdns_discover(registry))
            if ENABLE_SSDP:
                tasks.append(ssdp_discover(registry))
            if ENABLE_SNAPMAKER:
                tasks.append(snapmaker_discover(registry))

            if tasks:
                await asyncio.gather(*tasks)

            now = time.time()
            if ENABLE_PING and (now - last_ping_run >= PING_SWEEP_INTERVAL):
                await ping_sweep(registry)
                last_ping_run = now

        except Exception as e:
            log.warning(f"Loop error: {e}")

        await asyncio.sleep(SCAN_LOOP_INTERVAL)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
```

### Notes
- mDNS inside Docker Desktop on macOS is **best-effort** (multicast may not traverse the VM boundary). We still attempt short browse windows for `_http._tcp`, `_ipp._tcp`, etc. For more robust mDNS, see [macOS notes & options](#macos-notes--options).
- SSDP (M-SEARCH) and Snapmaker (UDP 20054 broadcast `"discover"`) are **active** queries and commonly work across NAT.
- ICMP uses `icmplib` with `privileged=True`. The container should be granted `CAP_NET_RAW`. 🔐 [Docker `cap_add` NET_RAW](https://www.google.com/search?q=docker+cap_add+NET_RAW+ping)

---

## Dockerfile

**`services/discovery/Dockerfile`**
```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps (minimal)
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 iputils-ping netcat-traditional tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/discovery/requirements.txt ./
RUN pip install -r requirements.txt

COPY services/discovery/app.py ./

EXPOSE 8088
CMD ["python", "app.py"]
```

**`services/discovery/requirements.txt`**
```
fastapi>=0.114
uvicorn>=0.30
redis>=5.0
zeroconf>=0.132
icmplib>=3.0
```

---

## Docker Compose

**`docker-compose.discovery.yml`**
```yaml
version: "3.9"

services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped

  discovery:
    build:
      context: .
      dockerfile: services/discovery/Dockerfile
    env_file:
      - ./.env.discovery
    cap_add:
      - NET_RAW
    depends_on:
      - redis
    ports:
      - "8088:8088"   # optional: inspect /devices from host
    restart: unless-stopped
```

> Using the default bridge network on macOS. Active discovery (SSDP, Snapmaker broadcast, ICMP) is the reliable baseline here.

---

## Build & run

```bash
# from repo root (where docker-compose.discovery.yml lives)
docker compose -f docker-compose.discovery.yml build discovery
docker compose -f docker-compose.discovery.yml up -d

# view logs
docker compose -f docker-compose.discovery.yml logs -f discovery
```

---

## Verification

1. **Health**  
   ```bash
   curl http://localhost:8088/health
   ```

2. **Devices JSON** (may be empty on first run; give it ~1–2 minutes)  
   ```bash
   curl http://localhost:8088/devices | jq
   ```

3. **Redis keys**  
   ```bash
   docker exec -it $(docker ps -qf name=redis) redis-cli --scan --pattern "device:*"
   ```

4. **Force a sweep** (temporarily lower intervals in `.env.discovery`, then `docker compose up -d` again).

5. **Snapmaker only smoke test** (broadcast on 20054; should log replies if a Snapmaker is present).

---

## Integration ideas

- **Orchestration hook:** subscribe your controller to Redis channel `events:printer_idle` to pick up Snapmaker transitions (IDLE). 🔴 [Redis Pub/Sub Python](https://www.google.com/search?q=redis+python+pubsub+example)
- **Device registry API:** keep using `/devices` for the UI; or have your main API aggregate Redis.
- **Type heuristics:** tweak `classify_mdns()` to pattern-match names specific to your fleet (e.g., Bambu model codenames).

---

## macOS notes & options

- Docker Desktop on macOS does **not** provide true host networking, and multicast (mDNS/SSDP) is not fully visible within containers. 🍎 [Host networking macOS context](https://www.google.com/search?q=Docker+Desktop+Mac+host+networking+multicast+not+supported)
- **Option A (recommended baseline):** rely on **active** discovery (SSDP/Snapmaker/ping) — already implemented above.
- **Option B (advanced):** run a small **Linux VM** bridged to your LAN, deploy the same container with `--network=host`, and point it at the same Redis (published by your Mac). This enables full mDNS/SSDP multicast. 🖧 [Bridged VM multicast docker](https://www.google.com/search?q=bridge+vm+multicast+docker+mdns+ssdp)
- **Option C (experimental):** run an mDNS/SSDP repeater/relay on the host to forward packets between the host NIC and the Docker bridge. 🔁 [mDNS repeater container](https://www.google.com/search?q=docker+mdns+repeater+forward+multicast)

---

## Troubleshooting

- **No devices found:** verify `DISCOVERY_SUBNETS` matches your LAN (e.g., `ipconfig getifaddr en0` / router CIDR).  
- **Ping sweep empty:** container needs `CAP_NET_RAW`. Ensure `cap_add: [NET_RAW]` and that ICMP isn’t blocked by devices.  
- **Snapmaker missing:** confirm the device is on the same subnet; check firewall; try increasing `SNAPMAKER_TIMEOUT`.  
- **mDNS sparse:** expected on macOS with Docker; try Option B/C above. Also, increase the mDNS browse window (change `await asyncio.sleep(3.0)` → `5.0–10.0`).  
- **High CPU during sweeps:** widen `PING_SWEEP_INTERVAL`, or limit subnets.  
- **Multiple networks:** set `DISCOVERY_SUBNETS=192.168.1.0/24,192.168.50.0/24` and ensure routing reaches them.  
- **Apple Silicon images:** all provided images are multi-arch; Docker Desktop pulls arm64 automatically.  

---

## See also

- 🌐 [Bonjour / Zeroconf fundamentals](https://www.google.com/search?q=zeroconf+bonjour+mdns+overview) — background on service discovery
- 📡 [SSDP M-SEARCH examples](https://www.google.com/search?q=python+ssdp+m-search+example) — craft and parse SSDP in Python
- 🧪 [Snapmaker discovery protocol hints](https://www.google.com/search?q=Snapmaker+Luban+UDP+20054+discover) — practical notes from the community
- 🦈 [Scapy ARP scanning](https://www.google.com/search?q=scapy+arp+scan+example) — alternative L2 discovery (best on Linux host/VM)
- 🧰 [python-zeroconf usage](https://www.google.com/search?q=python+zeroconf+library+usage) — browse service types and records

## You may also enjoy

- 🧭 [Home network CIDR & gateway basics](https://www.google.com/search?q=how+to+find+home+network+cidr+on+mac) — confirm the right subnet
- 🧱 [Firewall tips for local discovery](https://www.google.com/search?q=macos+firewall+allow+udp+broadcast+multicast) — when broadcasts seem blocked
- 🧩 [Redis keys & TTL patterns](https://www.google.com/search?q=redis+key+design+ttl+best+practices) — keep the registry clean over time
```

