#!/usr/bin/env bash
# Host-native discovery runner (macOS-friendly) to capture LAN MACs/OUI.
# Uses the repo .venv and local Postgres (forwarded from Docker compose).

set -euo pipefail

# Resolve project root (script lives in ops/scripts/discovery)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
VENV="$PROJECT_ROOT/.venv"
OUI_FILE="$PROJECT_ROOT/config/oui.manuf"

# Detect primary subnet (macOS: en0). Fallback to 192.168.0.0/24.
detect_subnet() {
  if command -v ipconfig >/dev/null 2>&1; then
    ip=$(ipconfig getifaddr en0 || true)
    if [[ -n "${ip:-}" ]]; then
      IFS=. read -r a b c _ <<<"$ip"
      echo "${a}.${b}.${c}.0/24"
      return
    fi
  fi
  echo "192.168.0.0/24"
}

SUBNETS="$(detect_subnet)"
SUBNETS_JSON="[\"$SUBNETS\"]"

if [[ ! -f "$OUI_FILE" ]]; then
  echo "OUI file not found at $OUI_FILE. Downloading Wireshark manuf..."
  mkdir -p "$(dirname "$OUI_FILE")"
  curl -fL https://www.wireshark.org/download/automated/data/manuf -o "$OUI_FILE"
fi

if [[ ! -x "$VENV/bin/python" ]]; then
  echo "Virtualenv not found at $VENV. Please create it first (python -m venv .venv && pip install -r requirements-dev.txt)."
  exit 1
fi

export PYTHONPATH="$PROJECT_ROOT"
export SETTINGS_MODULE=services.common.config
export OUI_DB_PATH="$OUI_FILE"

# Point to the compose Postgres on the host
export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export POSTGRES_USER="${POSTGRES_USER:-kitty}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-changeme}"
export POSTGRES_DB="${POSTGRES_DB:-kitty}"

# Discovery config tuned for host run
export DISCOVERY_ENABLE_NETWORK_SCAN=true
export DISCOVERY_SUBNETS="$SUBNETS_JSON"
export DISCOVERY_PING_PRIVILEGED=false   # avoid raw sockets on macOS
export DISCOVERY_ENABLE_PERIODIC_SCANS=true

do_arp_scan() {
  if ! command -v arp-scan >/dev/null 2>&1; then
    echo "[arp-scan] arp-scan not installed (brew install arp-scan) - skipping vendor labeling"
    return 0
  fi
  echo "[arp-scan] Root is required to read ARP tables. You will be prompted once."
  if ! sudo -v; then
    echo "[arp-scan] sudo failed or aborted; skipping"
    return 0
  fi
  echo "[arp-scan] Running sudo arp-scan -l ..."
  if ! output=$(sudo arp-scan -l 2>/dev/null); then
    echo "[arp-scan] arp-scan failed; skipping"
    return 0
  }
  payload="{\"entries\":["
  first=1
  while IFS= read -r line; do
    ip=$(echo "$line" | awk '{print $1}')
    mac=$(echo "$line" | awk '{print $2}')
    vendor=$(echo "$line" | cut -d' ' -f3-)
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ && "$mac" =~ : ]]; then
      # Skip broadcast/summary lines
      if [[ "$ip" == "Interface:" || "$ip" == "Ending" || "$ip" == "Address" ]]; then
        continue
      fi
      if [ $first -eq 0 ]; then
        payload+=","
      fi
      first=0
      vendor_esc=${vendor//\"/}
      payload+="{\"ip_address\":\"$ip\",\"mac_address\":\"$mac\",\"vendor\":\"$vendor_esc\"}"
    fi
  done <<< "$output"
  payload+="]}"

  echo "[arp-scan] Posting ARP entries to discovery..."
  curl -sf -X POST -H "Content-Type: application/json" -d "$payload" http://localhost:8500/api/discovery/arp || true
}

echo "Running discovery on host network (subnets=$DISCOVERY_SUBNETS)..."
cd "$PROJECT_ROOT"
# Kick off arp-scan once before starting uvicorn (optional)
do_arp_scan

exec "$VENV/bin/uvicorn" services.discovery.src.discovery.app:app --host 0.0.0.0 --port 8500
