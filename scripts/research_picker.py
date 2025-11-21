#!/usr/bin/env python3
"""
Lightweight picker/exporter for KITTY research sessions.

Features:
- Lists recent research sessions (via /api/research/sessions).
- Lets you pick a session ID (numbered list or direct ID).
- Exports the session to a Markdown file formatted with the GPTOSS template.
- Optionally opens the file in a terminal editor/pager (nano/less/glow/etc.).

Environment:
- KITTY_API_BASE : API root (default http://localhost:8000)
- KITTY_USER_ID  : User ID filter (defaults to derived CLI user)
- KITTY_USER_NAME: Used as Researcher name in metadata (optional)
- EDITOR         : Editor/pager if --open is provided (fallback: nano, then less -R)

Usage:
  python scripts/research_picker.py                     # interactive picker
  python scripts/research_picker.py SESSION_ID          # export specific session
  python scripts/research_picker.py --limit 30 --open   # pick from 30 sessions and open
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError, HTTPError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

# Defaults match the existing CLI behavior
API_BASE = os.getenv("KITTY_API_BASE", "http://localhost:8000")
USER_NAME = os.getenv("KITTY_USER_NAME", os.getenv("USER", "ssh-operator"))
USER_ID = os.getenv(
    "KITTY_USER_ID",
    str(uuid.uuid5(uuid.NAMESPACE_DNS, USER_NAME)),
)


def _fetch_json(path: str) -> Dict[str, Any]:
    """GET a JSON endpoint relative to API_BASE."""
    url = f"{API_BASE}{path}"
    req = Request(url)
    with urlopen(req, timeout=30) as resp:
        return json.load(resp)


def list_sessions(limit: int) -> List[Dict[str, Any]]:
    """List recent research sessions for the current user."""
    try:
        data = _fetch_json(f"/api/research/sessions?user_id={quote_plus(USER_ID)}&limit={limit}")
    except (HTTPError, URLError) as exc:  # noqa: PERF203 - explicit readability
        print(f"Error: could not list sessions ({exc})", file=sys.stderr)
        return []
    return data.get("sessions", [])


def pick_session(sessions: List[Dict[str, Any]]) -> Optional[str]:
    """Prompt user to pick a session from a numbered list or enter an ID."""
    if not sessions:
        return None

    print("\nRecent research sessions:\n")
    for idx, sess in enumerate(sessions, 1):
        sid = sess.get("session_id", "")
        status = sess.get("status", "unknown")
        query = (sess.get("query") or "").replace("\n", " ")
        print(f"{idx:>2}. {sid} [{status}] {query[:100]}{'…' if len(query) > 100 else ''}")

    print()
    choice = input("Enter number or session ID (blank to cancel): ").strip()
    if not choice:
        return None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(sessions):
            return sessions[idx - 1].get("session_id")
        print(f"Invalid number: {choice}", file=sys.stderr)
        return None
    return choice


def load_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Fetch session detail and results."""
    try:
        detail = _fetch_json(f"/api/research/sessions/{session_id}")
        results = _fetch_json(f"/api/research/sessions/{session_id}/results")
        return {"detail": detail, "results": results}
    except (HTTPError, URLError) as exc:
        print(f"Error: could not load session {session_id} ({exc})", file=sys.stderr)
        return None


def _safe(val: Any, default: str = "N/A") -> str:
    """Stringify with N/A fallback."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return str(val)
    text = str(val).strip()
    return text if text else default


def render_report(detail: Dict[str, Any], results: Dict[str, Any]) -> str:
    """Render a session into the GPTOSS template."""
    now = datetime.now(timezone.utc)
    created_at = detail.get("created_at") or now.isoformat()
    config = detail.get("config") or {}

    # Basic metrics
    total_findings = results.get("total_findings", 0)
    total_sources = results.get("total_sources", 0)
    total_cost = results.get("total_cost_usd", 0.0)
    final_synthesis = results.get("final_synthesis") or "N/A"

    # Findings preview (short)
    findings = results.get("findings") or []
    sample_findings = []
    for idx, finding in enumerate(findings[:3], 1):
        content = finding.get("content", "") or ""
        snippet = content[:500] + ("…" if len(content) > 500 else "")
        sample_findings.append(f"Finding {idx}: {snippet}")
    findings_block = "\n".join(sample_findings) if sample_findings else "N/A"

    # Config decoding defaults
    temperature = config.get("temperature", "N/A")
    top_p = config.get("top_p", "N/A")
    max_tokens = config.get("max_output_tokens") or config.get("max_tokens") or "N/A"
    stop_sequences = config.get("stop_sequences") or "N/A"
    strategy = config.get("strategy", "N/A")

    # Representative outputs block
    rep_outputs = [
        "Synthesis:\n" + final_synthesis,
    ]
    if sample_findings:
        rep_outputs.append("\n".join(sample_findings))
    rep_block = "\n\n".join(rep_outputs) if rep_outputs else "N/A"

    report = f"""
<LLM_RESEARCH_OUTPUT>

# 0. METADATA
Run_ID: {detail.get('session_id', 'N/A')}
Date: {created_at[:10]}
Researcher: {USER_NAME}
Model_Name: GPTOSS-120B
Model_Revision: N/A
KITTY_Pipeline_Stage: analysis
Dataset_Name: research_sessions
Task_Type: research
Experiment_Tag: strategy={strategy}

# 1. RESEARCH QUESTION
Primary_Question: {_safe(detail.get('query'))}
Secondary_Questions:
- N/A
- N/A

# 2. HYPOTHESES
Null_Hypothesis: N/A
Working_Hypotheses:
- H1: N/A
- H2: N/A
- H3: N/A

# 3. EXPERIMENT DESIGN

## 3.1 Variables
Independent_Variables:
- strategy: {strategy}
- max_iterations: {_safe(config.get('max_iterations', 'N/A'))}
Dependent_Variables:
- findings: total findings collected
- cost_usd: total cost in USD

## 3.2 Model Configuration
Temperature: {temperature}
Top_p: {top_p}
Max_Tokens: {max_tokens}
Stop_Sequences: {stop_sequences}
System_Prompt_Summary: N/A
Other_Params: {json.dumps(config)}

## 3.3 Data & Sampling
Input_Source: web + tools
Sample_Size: {total_findings}
Sampling_Strategy: iterative search
Train_Dev_Test_Split: N/A
Filtering_Notes:
- N/A
- N/A

# 4. PROMPT SETUP

## 4.1 System Prompt (verbatim)
<BEGIN_BLOCK:SYSTEM_PROMPT>
N/A
<END_BLOCK:SYSTEM_PROMPT>

## 4.2 User Prompt / Template (verbatim)
<BEGIN_BLOCK:USER_PROMPT_TEMPLATE>
N/A
<END_BLOCK:USER_PROMPT_TEMPLATE>

## 4.3 Few-Shot Examples
Has_Few_Shot: no
<BEGIN_BLOCK:FEW_SHOT_EXAMPLES>
N/A
<END_BLOCK:FEW_SHOT_EXAMPLES>

# 5. RESULTS

## 5.1 Quantitative Results
Metrics:
- total_findings: {total_findings} (all)
- total_sources: {total_sources} (all)
- total_cost_usd: {total_cost:.4f} (all)
Aggregate_Summary:
- Findings collected: {total_findings}
- Sources referenced: {total_sources}
- Spend: ${total_cost:.4f}

## 5.2 Qualitative Results
Representative_Outputs:
<BEGIN_BLOCK:REPRESENTATIVE_OUTPUTS>
{rep_block}
<END_BLOCK:REPRESENTATIVE_OUTPUTS>

Error_Patterns:
- N/A
- N/A

# 6. ANALYSIS

Interpretation:
- Session status: {_safe(detail.get('status'))}
- Completeness score: {_safe(results.get('completeness_score'))}
- Confidence score: {_safe(results.get('confidence_score'))}

Surprises:
- N/A

Threats_to_Validity:
- Internal: N/A
- External: Findings not audited; relies on upstream sources

# 7. DECISIONS & NEXT STEPS
Decisions:
- N/A

Followup_Experiments:
- Run further iterations if findings are sparse
- N/A

Notes_for_KITTY_Pipeline:
- Session exported from CLI picker
- N/A

# 8. RAW LOG / TRACE (OPTIONAL)
<BEGIN_BLOCK:RAW_LOG>
N/A
<END_BLOCK:RAW_LOG>

</LLM_RESEARCH_OUTPUT>
"""
    return report.strip() + "\n"


def write_report(report: str, session_id: str, out_dir: Path) -> Path:
    """Write report to disk and return path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{session_id}.md"
    path.write_text(report, encoding="utf-8")
    return path


def open_in_editor(path: Path, editor: Optional[str]) -> None:
    """Open the file in a terminal editor/pager."""
    if editor:
        cmd = shlex.split(editor)
    else:
        cmd = shlex.split(os.getenv("EDITOR", "")) if os.getenv("EDITOR") else []
    if not cmd:
        cmd = ["nano"]
    cmd += [str(path)]
    try:
        subprocess.run(cmd, check=False)
    except FileNotFoundError:
        # Fallback to less -R if the chosen editor is missing
        subprocess.run(["less", "-R", str(path)], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export KITTY research sessions into a GPTOSS template report.")
    parser.add_argument("session_id", nargs="?", help="Session ID to export (leave blank for picker)")
    parser.add_argument("--limit", type=int, default=15, help="How many sessions to list in picker")
    parser.add_argument("--output-dir", default="Research/exports", help="Where to save reports")
    parser.add_argument("--open", action="store_true", help="Open the exported file in EDITOR/nano/less")
    parser.add_argument("--editor", help="Explicit editor/pager command (e.g., 'glow', 'nano', 'less -R')")
    args = parser.parse_args()

    session_id = args.session_id
    if not session_id:
        sessions = list_sessions(args.limit)
        session_id = pick_session(sessions)
        if not session_id:
            print("No session selected; exiting.")
            return

    payload = load_session(session_id)
    if not payload:
        return

    report = render_report(payload["detail"], payload["results"])
    out_path = write_report(report, session_id, Path(args.output_dir))
    print(f"\nSaved report to {out_path}")

    if args.open:
        open_in_editor(out_path, args.editor)


if __name__ == "__main__":
    main()
