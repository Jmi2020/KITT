# KITTY Command Broker

Safe terminal access for a locally hosted model to run scripts and open select programs on macOS.

**Goal:** Give KITTY (your local LLM) the ability to execute only what you approve—scripts and apps—without exposing a raw shell, while enforcing least-privilege, confirmations for hazardous actions, and full audit logging.

---

## Table of Contents

- [Why a Command Broker (Problem → Solution)](#why-a-command-broker-problem--solution)
- [Security Principles](#security-principles)
- [System Architecture](#system-architecture)
- [Requirements and Tech Choices](#requirements-and-tech-choices)
- [Directory Layout](#directory-layout)
- [Implementation Steps](#implementation-steps)
  - [6.1 Create Service User](#61-create-service-user)
  - [6.2 Install Broker and Python Dependencies](#62-install-broker-and-python-dependencies)
  - [6.3 Command Allow-list (YAML)](#63-command-allow-list-yaml)
  - [6.4 Broker API (FastAPI) Reference Implementation](#64-broker-api-fastapi-reference-implementation)
  - [6.5 Sample Scripts](#65-sample-scripts)
  - [6.6 launchd Services (Daemon and Agent)](#66-launchd-services-daemon-and-agent)
  - [6.7 TCC Automation and Accessibility](#67-tcc-automation-and-accessibility)
  - [6.8 Optional sudoers Configuration](#68-optional-sudoers-configuration)
- [API Contracts for KITTY Tool Calls](#api-contracts-for-kitty-tool-calls)
- [Observability and Audit Logging](#observability-and-audit-logging)
- [Safety: Two-Step Confirmation and Zones](#safety-two-step-confirmation-and-zones)
- [Security and Threat Model](#security-and-threat-model)
- [Testing and Pen-Tests](#testing-and-pen-tests)
- [Makefile, Environment, and Quickstart](#makefile-environment-and-quickstart)
- [Future Extensions](#future-extensions)
- [References](#references)
- [Hand-off to the Coding Agent](#hand-off-to-the-coding-agent)

---

## Why a Command Broker (Problem → Solution)

- **Problem:** An LLM with terminal access is dangerous: arbitrary shell execution, privilege escalation, or lateral movement.
- **Solution:** Run a small Command Broker process under a restricted user. Expose a local HTTP or UNIX-socket API that executes only allow-listed commands with validated arguments and timeouts. KITTY invokes structured tools, never a raw shell.

---

## Security Principles

- Least privilege via a dedicated `kitty-runner` user outside the admin group.
- Deny-by-default semantics; only allow-listed commands with JSON Schema validation.
- No shell execution (`subprocess.run(shell=False)` with fixed absolute paths).
- Safety gates enforce two-step confirmation for hazardous intents.
- Isolation by separating LaunchDaemon (headless) from LaunchAgent (GUI session).
- Structured audit logging that captures who/what/when/args/exit codes.
- Optional tamper resistance with code signing and immutable script directories.

---

## System Architecture

```text
[KITTY LLM] --(tool call JSON)--> [Command Broker API]
    |                                   |
    |                      validates allow-list + JSON schema
    |                                   v
   UI (Open WebUI)                [Exec Runner]
                                 /     |      \
                                /      |       \
                   [Scripts: CAD/print]  [App Launcher]  [Optional sudoers cmds]
```

- Broker runs as `kitty-runner` with minimal privileges.
- LaunchDaemon (headless) handles scripts; LaunchAgent (per-user) handles GUI app launches.
- Logs flow to files and macOS unified logging; metrics forward to your observability stack.

---

## Requirements and Tech Choices

- **Language:** Python 3.11 (FastAPI, Pydantic, jsonschema).
- **Process Model:** `subprocess.run` with explicit argv lists, no shell expansion.
- **Configuration:** YAML allow-list per command with JSON Schema for argument validation.
- **Transport:** Localhost HTTP or (preferably) UNIX domain socket.
- **Persistence:** `/var/log/kitty-broker/` stores structured logs; optional Grafana/Loki integration.
- **macOS Services:** `launchd` provides supervision; TCC Automation/Accessibility grants GUI control.

### Helpful Background Reading

- FastAPI primer
- Pydantic v2 reference
- JSON Schema documentation
- macOS launchd (LaunchDaemon vs LaunchAgent)
- macOS TCC Automation and Accessibility permissions

---

## Directory Layout

```text
/opt/kitty/
  bin/                  # compiled helpers (owned root:wheel, 0755)
  scripts/              # python/sh scripts (root:wheel, 0755)
  broker/
    broker.py           # FastAPI app
    pyproject.toml
    requirements.txt
/etc/kitty-broker/
  commands.yml          # allow-list + JSON schemas
/var/log/kitty-broker/
  broker.jsonl
  broker.err.log
/var/run/kitty-work/    # ephemeral working dir
/Library/LaunchDaemons/com.kitty.broker.plist
/Library/LaunchAgents/com.kitty.agent.plist
```

---

## Implementation Steps

### 6.1 Create Service User

```bash
sudo dscl . -create /Users/kitty-runner
sudo dscl . -create /Users/kitty-runner UserShell /usr/bin/false
sudo dscl . -create /Users/kitty-runner RealName "KITTY Runner"
sudo dscl . -create /Users/kitty-runner UniqueID 550
sudo dscl . -create /Users/kitty-runner PrimaryGroupID 20
sudo dscl . -create /Users/kitty-runner NFSHomeDirectory /var/empty
sudo dscl . -append /Groups/nobody GroupMembership kitty-runner  # optional isolation
sudo mkdir -p /var/run/kitty-work /var/log/kitty-broker /opt/kitty/{bin,scripts,broker}
sudo chown -R root:wheel /opt/kitty /etc/kitty-broker /var/log/kitty-broker /var/run/kitty-work
sudo chmod -R 0755 /opt/kitty /var/run/kitty-work
sudo chmod 0750 /var/log/kitty-broker
```

### 6.2 Install Broker and Python Dependencies

`/opt/kitty/broker/requirements.txt`

```text
fastapi==0.115.*
uvicorn[standard]==0.30.*
pydantic==2.*
jsonschema==4.*
python-json-logger==2.*
```

```bash
python3 -m venv /opt/kitty/broker/.venv
source /opt/kitty/broker/.venv/bin/activate
pip install -r /opt/kitty/broker/requirements.txt
```

### 6.3 Command Allow-list (YAML)

`/etc/kitty-broker/commands.yml`

```yaml
commands:
  convert_stl:
    cmd: ["/opt/kitty/bin/mesh-tool"]
    args_schema:
      type: object
      required: ["input", "output"]
      additionalProperties: false
      properties:
        input:  {type: "string", pattern: "^/data/[^\\0]+\\.step$"}
        output: {type: "string", pattern: "^/data/[^\\0]+\\.stl$"}
    timeout_sec: 120

  run_cadquery:
    cmd: ["/usr/bin/python3", "/opt/kitty/scripts/run_cadquery.py"]
    args_schema:
      type: object
      required: ["model", "params"]
      additionalProperties: false
      properties:
        model:  {type: "string", enum: ["bracket", "panel", "gear"]}
        params: {type: "object"}
    timeout_sec: 180

  open_app:
    cmd: ["/usr/bin/open", "-a"]  # handled by LaunchAgent instance
    args_schema:
      type: object
      required: ["app", "args"]
      additionalProperties: false
      properties:
        app:  {type: "string", enum: ["Fusion 360", "PrusaSlicer", "Visual Studio Code"]}
        args:
          type: "array"
          items: {type: "string", maxLength: 128}
          maxItems: 6
    timeout_sec: 10
```

### 6.4 Broker API (FastAPI) Reference Implementation

`/opt/kitty/broker/broker.py`

```python
import os
import pwd
import json
import time
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from jsonschema import validate, ValidationError
from pythonjsonlogger import jsonlogger
import yaml

# ---- Config ----
CFG = yaml.safe_load(open("/etc/kitty-broker/commands.yml"))
BROKER_UID = pwd.getpwnam("kitty-runner").pw_uid
WORKDIR = "/var/run/kitty-work"
LOG_DIR = Path("/var/log/kitty-broker")
LOG_FILE = LOG_DIR / "broker.jsonl"

# ---- Logging ----
logger = jsonlogger.JsonFormatter("%(message)s")


def log(entry: dict) -> None:
    entry["ts"] = time.time()
    with open(LOG_FILE, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


# ---- Models ----
class ExecReq(BaseModel):
    command: str
    args: dict
    request_id: str | None = None


class ExecResp(BaseModel):
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int


app = FastAPI()


def validate_localhost(req: Request) -> None:
    # Accept only loopback connections (or UNIX socket deployment)
    if req.client and req.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "forbidden")


def build_argv(spec: dict, args: dict) -> list[str]:
    # No shell; cmd must be absolute paths / fixed tokens
    argv = list(spec["cmd"])
    if argv == ["/usr/bin/open", "-a"]:
        argv += [args["app"], "--args"] + args["args"]
    else:
        argv += [json.dumps(args)]
    return argv


@app.post("/exec", response_model=ExecResp)
async def exec_cmd(req: ExecReq, raw: Request) -> ExecResp:
    validate_localhost(raw)
    spec = CFG["commands"].get(req.command)
    if not spec:
        raise HTTPException(403, "command not allowed")

    try:
        validate(instance=req.args, schema=spec["args_schema"])
    except ValidationError as exc:
        raise HTTPException(400, f"bad args: {exc.message}") from exc

    argv = build_argv(spec, req.args)
    env = {"PATH": "/usr/bin:/bin"}

    start = time.time()
    try:
        proc = subprocess.run(
            argv,
            cwd=WORKDIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=spec.get("timeout_sec", 60),
            shell=False,
            preexec_fn=lambda: os.setuid(BROKER_UID),
        )
    except subprocess.TimeoutExpired:
        log(
            {
                "level": "warn",
                "event": "timeout",
                "cmd": req.command,
                "args": req.args,
                "rid": req.request_id,
            }
        )
        raise HTTPException(504, "timeout") from None

    duration = int((time.time() - start) * 1000)
    entry = {
        "level": "info",
        "event": "exec",
        "rid": req.request_id,
        "cmd": req.command,
        "args": req.args,
        "rc": proc.returncode,
        "ms": duration,
        "out_len": len(proc.stdout or ""),
        "err_len": len(proc.stderr or ""),
    }
    log(entry)

    return ExecResp(
        returncode=proc.returncode,
        stdout=(proc.stdout or "")[-4096:],
        stderr=(proc.stderr or "")[-4096:],
        duration_ms=duration,
    )


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True}
```

Run the service in development mode:

```bash
source /opt/kitty/broker/.venv/bin/activate
uvicorn broker:app --host 127.0.0.1 --port 8777 --workers 1
```

### 6.5 Sample Scripts

CadQuery runner — `/opt/kitty/scripts/run_cadquery.py`

```python
#!/usr/bin/env python3
import sys
import json
import cadquery as cq

args = json.loads(sys.argv[1])
model, params = args["model"], args["params"]

if model == "bracket":
    width = params.get("width", 50)
    height = params.get("height", 30)
    thickness = params.get("thickness", 3)
    part = (
        cq.Workplane("XY")
        .box(width, thickness, thickness)
        .faces(">Z")
        .workplane()
        .rect(width, thickness / 2)
        .extrude(height)
    )
elif model == "panel":
    width = params["width"]
    height = params["height"]
    thickness = params.get("thickness", 2)
    part = cq.Workplane("XY").box(width, height, thickness)
elif model == "gear":
    raise SystemExit("gear not implemented")
else:
    raise SystemExit(f"unknown model {model}")

output_path = params.get("out", "/var/run/kitty-work/out.step")
part.val().exportStep(output_path)
print(output_path)
```

```bash
chmod 0755 /opt/kitty/scripts/run_cadquery.py
```

Mesh converter stub — `/opt/kitty/bin/mesh-tool`
(Replace with your compiled tool; the broker treats it as a fixed binary.)

### 6.6 launchd Services (Daemon and Agent)

**Daemon (headless scripts)** — `/Library/LaunchDaemons/com.kitty.broker.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.kitty.broker</string>
  <key>UserName</key><string>kitty-runner</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/kitty/broker/.venv/bin/uvicorn</string>
    <string>broker:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8777</string>
    <string>--workers</string><string>1</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/var/log/kitty-broker/broker.out.log</string>
  <key>StandardErrorPath</key><string>/var/log/kitty-broker/broker.err.log</string>
</dict></plist>
```

```bash
sudo launchctl load /Library/LaunchDaemons/com.kitty.broker.plist
```

**Agent (GUI app launch)** — `/Library/LaunchAgents/com.kitty.agent.plist`
Runs in the logged-in user session so `open -a` can control apps.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.kitty.agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/opt/kitty/broker/.venv/bin/uvicorn</string>
    <string>broker:app</string>
    <string>--host</string><string>127.0.0.1</string>
    <string>--port</string><string>8778</string>
    <string>--workers</string><string>1</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/var/log/kitty-broker/agent.out.log</string>
  <key>StandardErrorPath</key><string>/var/log/kitty-broker/agent.err.log</string>
</dict></plist>
```

```bash
launchctl load /Library/LaunchAgents/com.kitty.agent.plist
```

### 6.7 TCC Automation and Accessibility

- The first GUI app launch may prompt for Automation or Accessibility access. Approve only the Agent process, not the Daemon.
- Review Apple documentation for macOS TCC Automation and the Accessibility API.

### 6.8 Optional sudoers Configuration

Grant only precise commands (no wildcards) with pinned arguments:

```bash
sudo visudo
```

Add:

```text
Cmnd_Alias KITTY_SAFE = /usr/sbin/softwareupdate --install --all
kitty-runner ALL=(root) NOPASSWD: KITTY_SAFE
```

Consult best practices for sudoers allow-list configuration if broader elevation is required.

---

## API Contracts for KITTY Tool Calls

**POST `/exec`**

Request body:

```json
{
  "request_id": "uuid-... (optional)",
  "command": "run_cadquery",
  "args": {
    "model": "bracket",
    "params": {
      "width": 60,
      "height": 40,
      "thickness": 3,
      "out": "/var/run/kitty-work/bracket.step"
    }
  }
}
```

Example response:

```json
{
  "returncode": 0,
  "stdout": "/var/run/kitty-work/bracket.step",
  "stderr": "",
  "duration_ms": 842
}
```

**GET `/healthz`** returns:

```json
{ "ok": true }
```

Routing guidelines inside KITTY:

- Headless/script actions → `http://127.0.0.1:8777/exec`
- GUI/app launches → `http://127.0.0.1:8778/exec`

Restrict access to loopback (see `validate_localhost`). Prefer a UNIX socket deployment if you want to avoid TCP entirely.

---

## Observability and Audit Logging

- JSONL event log at `/var/log/kitty-broker/broker.jsonl` (one entry per execution).
- Suggested fields: `ts`, `rid`, `cmd`, `args`, `rc`, `ms`, `out_len`, `err_len`.
- Forward logs to Grafana/Loki or Elastic for dashboards and alerting.
- Reference: Loki JSON line ingestion examples.

---

## Safety: Two-Step Confirmation and Zones

- KITTY classifies intents as `SAFE`, `CAUTION`, or `HAZARDOUS`.
- Hazardous actions (welder enable, laser fire, door unlock) require:
  1. User confirmation phrase (for example, "Confirm: proceed").
  2. Zone presence verification (camera or sensor).
  3. Interlocks reporting closed.
  4. Broker executes a single-purpose command for a bounded duration.

Implement policy enforcement in KITTY and pair it with narrowly defined broker commands (for example, `enable_welder`) constrained by JSON Schema.

---

## Security and Threat Model

- **Threats:** Prompt injection leading to arbitrary shell execution, path traversal, runaway processes, privilege escalation, or abusive UI scripting.
- **Mitigations:**
  - No shell invocation; enforce absolute paths and JSON Schema validation.
  - Fixed working directory; reject patterns such as `..`, `~`, `$()`.
  - Apply timeouts and optional CPU/memory caps (`ulimit`, `taskpolicy`, `nice`).
  - Separate daemon (headless) and agent (GUI); grant TCC permissions only to the agent.
  - Optional sandboxing via `sandbox-exec` profiles or third-party tools.
  - Code signing for the broker and helper binaries.
  - Minimal or no sudoers allowances.
  - Localhost or UNIX-socket only; optionally add HMAC or JWT headers between KITTY and the broker.

---

## Testing and Pen-Tests

1. Unit tests for JSON Schema definitions (accept and reject cases).
2. Path traversal attempts such as `../../etc/passwd` must be rejected.
3. Injection payloads containing `;`, backticks, `$()`, `|` must fail (schema + no shell).
4. Long-running scripts must trigger a `504` timeout and terminate the child process.
5. Disallowed app launches must return `403`.
6. Hazardous flows must refuse execution without the "Confirm: proceed" signal from KITTY policy.
7. TCC prompts must only appear for the Agent.
8. Log integrity: verify every execution is logged, rotated, and protected.

Helpful search queries: Python subprocess security without shells, JSON Schema validation examples.

---

## Makefile, Environment, and Quickstart

### `.env` (optional)

```text
BROKER_PORT_DAEMON=8777
BROKER_PORT_AGENT=8778
CONFIRM_PHRASE=Confirm: proceed
```

### Makefile

```makefile
PY = /opt/kitty/broker/.venv/bin/python
UV = /opt/kitty/broker/.venv/bin/uvicorn

.PHONY: install run-daemon run-agent logs

install:
	python3 -m venv /opt/kitty/broker/.venv
	. /opt/kitty/broker/.venv/bin/activate && pip install -r /opt/kitty/broker/requirements.txt

run-daemon:
	$(UV) broker:app --host 127.0.0.1 --port $(BROKER_PORT_DAEMON) --workers 1

run-agent:
	$(UV) broker:app --host 127.0.0.1 --port $(BROKER_PORT_AGENT) --workers 1

logs:
	tail -f /var/log/kitty-broker/broker.jsonl
```

### Smoke Test

```bash
curl -s http://127.0.0.1:8777/healthz

curl -s -X POST http://127.0.0.1:8777/exec \
  -H "Content-Type: application/json" \
  -d '{"command":"run_cadquery","args":{"model":"panel","params":{"width":80,"height":60,"thickness":2,"out":"/var/run/kitty-work/panel.step"}}}'
```

---

## Future Extensions

- Use UNIX domain sockets for both daemon and agent (eliminate TCP).
- Add command-level rate limits and circuit breakers.
- Require MFA for hazardous actions (for example, push approvals).
- Integrate a pluggable policy engine such as Open Policy Agent.
- Produce SBOMs and sign artifacts in `/opt/kitty/bin`.

---

## References

- Apple launchd (LaunchDaemon vs LaunchAgent)
- macOS TCC Automation permissions
- JSON Schema validation in Python
- FastAPI quickstart
- Python subprocess security without shells
- FastAPI JWT authentication patterns
- Loki JSON log ingestion
- Apple Accessibility and UI scripting
- Uvicorn with UNIX domain sockets

---

## Hand-off to the Coding Agent

- Implement the broker (FastAPI application plus dependencies).
- Create `commands.yml` and the sample helper scripts.
- Install the service as both LaunchDaemon (headless) and LaunchAgent (GUI).
- Approve TCC prompts only for the agent.
- Wire KITTY function calls to `/exec` (daemon) and `/exec` (agent) with two-step confirmation for hazardous actions.
- Add unit tests for schema validation and penetration-style tests for injections and timeouts.
