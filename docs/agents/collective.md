
# Collective Meta-Agent (Offline) — Operator Notes

**Routes**
- Gateway: `POST /api/collective/run`
- Agent Runtime: `POST /api/collective/run` (internal)

**Patterns**
- `pipeline` — uses coding graph if present, then judge synthesizes a final verdict
- `council` — K independent proposals (Q4), judged/summarized by F16
- `debate` — PRO vs CON one-round debate, judged by F16

**Usage (CLI)**
```bash
kitty-cli say "/agent on. call collective.run pattern=council k=3 to compare PETG vs ABS for Voron at 0.2mm."
```

**Notes**
- Stays offline (local llama.cpp only). No network calls.
- All proposals/judgments should be logged via existing Gateway/Brain audit patterns.
