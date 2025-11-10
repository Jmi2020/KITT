# KITTY Memory Safety Baselines

## Baseline: Before Model Stack Start (UTC 2025-11-10T05:54)
- Snapshot file: `.logs/memory/memory-20251110T055401Z.log`
- Load Avg: 4.27 / 4.43 / 4.01
- PhysMem: 246 GB used (5.5 GB wired, 2.1 GB compressed), 8.4 GB free
- Swap: 0 swapins / 0 swapouts
- Notes: Snapshot captured prior to launching the model stack.

## Baseline: After Model Stack Start (UTC 2025-11-10T05:54)
- Snapshot file: `.logs/memory/memory-20251110T055459Z.log`
- Load Avg: 3.42 / 4.15 / 3.93
- PhysMem: 246 GB used (5.6 GB wired, 2.1 GB compressed), 8.5 GB free
- Swap: 0 swapins / 0 swapouts
- Notes: llama.cpp servers listening on 8082/8083/8085 (plus Ollama 11434)

## Baseline: Post-Build & Gateway Restart (UTC 2025-11-10T06:03)
- Snapshot file: `.logs/memory/memory-20251110T060350Z.log`
- Load Avg: 2.58 / 2.86 / 3.30
- PhysMem: 245 GB used (5.1 GB wired, 2.1 GB compressed), 8.9 GB free
- Swap: 0 swapins / 0 swapouts
- Notes: System quiet with llama.cpp (8082/8083/8085) and Ollama (11434) listening.
