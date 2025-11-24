# Host-Native Discovery (macOS / LAN MAC visibility)

When the discovery service runs inside Docker Desktop, it cannot see LAN MACs (only the bridge). To label devices by manufacturer (OUI) on macOS, run discovery on the host.

## Prereqs
- `.venv` with project deps installed (`python -m venv .venv && source .venv/bin/activate && pip install -r requirements-dev.txt`).
- Compose stack running so Postgres is available on `localhost:5432` (default creds from `.env`).
- OUI file present at `config/oui.manuf` (script will download Wireshark manuf if missing).

## Run
```bash
./ops/scripts/discovery/run-host.sh
```

What it does:
- Detects your primary subnet (macOS `en0`) and sets `DISCOVERY_SUBNETS` (fallback `192.168.0.0/24`).
- Sets `DISCOVERY_PING_PRIVILEGED=false` to avoid raw-socket pings on macOS.
- Uses OUI db at `config/oui.manuf`.
- Connects to the compose Postgres on `localhost:5432`.
- Starts uvicorn on port `8500` (same API as the container).
- Stop the compose discovery container to avoid port conflicts, or change the port in `run-host.sh`.

## Notes
- After the host-run scan completes, `kitty-cli discover list` will show manufacturer/vendor for devices whose MACs are visible.
- To refresh OUI data: replace `config/oui.manuf` (Wireshark source: `https://www.wireshark.org/download/automated/data/manuf`) and restart the host-run.

## Optional: auto-start via launchd (macOS)
1) Copy `docs/runbooks/com.kitty.discovery.plist.sample` to `~/Library/LaunchAgents/com.kitty.discovery.plist`.
2) Edit the paths if your repo lives elsewhere.
3) Load once: `launchctl load ~/Library/LaunchAgents/com.kitty.discovery.plist`
4) Start now: `launchctl start com.kitty.discovery`
5) Logs: `tail -f ~/.logs/discovery-host.log`

To disable: `launchctl unload ~/Library/LaunchAgents/com.kitty.discovery.plist`.
