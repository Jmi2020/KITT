#!/usr/bin/env bash
# Consolidated snapshot of system + brain metrics.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
API_BASE="${KITTY_API_BASE:-http://localhost:8000}"
WATCHDOG_SCRIPT="$SCRIPT_DIR/llamacpp-watchdog.sh"
TIMESTAMP="$(date -u +"%Y-%m-%d %H:%M:%S UTC")"

print_section() {
  local title="$1"
  echo ""
  echo "=================================================="
  echo "$title"
  echo "=================================================="
}

echo "KITTY Metrics Dashboard | $TIMESTAMP"

print_section "System Memory"
if command -v top >/dev/null 2>&1; then
  top -l 1 | head -n 8 || true
else
  echo "top command not found"
fi

if command -v vm_stat >/dev/null 2>&1; then
  vm_stat | head -n 10 || true
else
  echo "vm_stat command not found"
fi

if command -v memory_pressure >/dev/null 2>&1; then
  memory_pressure || true
else
  echo "memory_pressure command not found"
fi

print_section "llama.cpp Processes"
if [[ -x "$WATCHDOG_SCRIPT" ]]; then
  "$WATCHDOG_SCRIPT"
else
  echo "Watchdog script not found at $WATCHDOG_SCRIPT"
fi

print_section "Brain Usage Metrics"
python3 <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = os.environ.get("KITTY_API_BASE", "http://localhost:8000").rstrip("/")

def fetch(path):
    url = f"{API_BASE}{path}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read()
            if not data:
                return None
            return json.loads(data)
    except urllib.error.URLError as exc:
        print(f"Failed to fetch {path}: {exc}")
        return None

usage = fetch("/api/usage/metrics")
if usage:
    print("Provider  | Tier      | Calls | Cost (USD) | Last Used")
    print("-" * 70)
    for provider in sorted(usage):
        entry = usage[provider]
        tier = entry.get("tier", "-")
        calls = entry.get("calls", 0)
        cost = entry.get("total_cost", 0.0)
        last_used = entry.get("last_used", "-")
        print(f"{provider:<9} {tier:<10} {calls:>5}   ${cost:>9.4f}   {last_used}")
else:
    print("No usage data available (service offline?).")

print("\nAutonomy Status (scheduled)")
status = fetch("/api/autonomy/status?workload=scheduled")
if status:
    fields = [
        ("Budget Available", status.get("budget_available")),
        ("Budget Used Today", status.get("budget_used_today")),
        ("CPU%", status.get("cpu_usage_percent")),
        ("Memory%", status.get("memory_usage_percent")),
        ("Can Run", status.get("can_run_autonomous")),
        ("Reason", status.get("reason")),
    ]
    for label, value in fields:
        print(f"  {label:<18}: {value}")
else:
    print("  Unable to fetch autonomy status.")

print("\nAutonomy Budget (3d)")
budget = fetch("/api/autonomy/budget?days=3")
if budget:
    print(f"  Total Cost USD : {budget.get('total_cost_usd')}")
    print(f"  Total Requests : {budget.get('total_requests')}")
    breakdown = budget.get("daily_breakdown", [])
    if breakdown:
        for day in breakdown:
            print(f"    {day.get('date')}: ${day.get('cost_usd')} ({day.get('requests')} reqs)")
else:
    print("  Unable to fetch budget summary.")
PY

echo ""
echo "Dashboard complete."
