# Claude Code Architecture Deep Dive: From Plan Mode to Offline Mistral Deployment

Claude Code implements a deliberately simple yet powerful **single-threaded master loop architecture** (internally codenamed "nO") that prioritizes debuggability over complexity. Plan mode operates as a read-only research phase where the only writable file is the plan document itself—enforced through prompt injection rather than hard-coded tool restrictions. The ralph-wiggum plugin extends this architecture with autonomous iteration loops, and these patterns translate effectively to offline Mistral deployments with specific adaptations for air-gapped security requirements.

---

## How Plan mode separates research from execution

Plan mode creates a **read-only environment** that prevents Claude from making codebase changes until the user explicitly approves a plan. When activated via `Shift+Tab` twice, Claude retains access to exploration tools (Read, LS, Glob, Grep) but cannot edit files or run destructive commands—with one critical exception: the plan file itself, stored as Markdown in `~/.claude/plans/`.

The restriction mechanism is remarkably elegant. Rather than removing write tools from the schema, Claude Code injects a system prompt override:

```
Plan mode is active. The user indicated that they do not want you to execute yet — 
you MUST NOT make any edits (with the exception of the plan file mentioned below), 
run any non-readonly tools... This supersedes any other instructions you have received.
```

This prompt-based constraint allows the agent to enter plan mode autonomously via a tool call, creating a flexible state machine. The plan file serves as the **state bridge** between planning and execution phases—Claude writes structured tasks to this Markdown document, exits plan mode by calling `exit_plan_mode`, and then reads the same file during execution to guide implementation.

Plan mode enforces a **four-phase workflow**: initial understanding (code exploration and clarifying questions), design (comprehensive implementation approach), review (alignment verification), and final plan (concise, actionable document with specific file paths). The TODO-based tracking system renders these phases as interactive checklists in the UI, with exactly one task marked `in_progress` at any time.

---

## The agentic loop: radical simplicity over complexity

Claude Code's master loop follows a classic pattern that Anthropic describes as "radical simplicity":

```
while(tool_call) → execute tool → feed results → repeat
```

The architecture deliberately avoids multi-agent swarms or competing personas. Instead, a **flat message history** maintains a single conversation thread, making debugging straightforward and state management predictable. Key components include the nO master loop engine, an h2A async dual-buffer queue for real-time steering (allowing users to inject new instructions mid-task), and a compressor (wU2) that auto-triggers at approximately **92% context usage** to summarize conversations.

Sub-agents provide controlled parallelism through the `dispatch_agent` tool, but with strict depth limitations—sub-agents cannot spawn their own sub-agents, preventing runaway recursion. Results feed back as regular tool outputs. This enables parallel codebase searches or trying multiple solution approaches while maintaining overall coherence.

The **checkpoint and rollback system** (introduced in v2.0.0) creates automatic checkpoints at every user prompt. Users can rewind via `Esc + Esc` with three options: conversation only (keep code changes), code only (keep conversation), or both. However, bash commands like `rm`, `mv`, and `cp` aren't tracked—these require git-level backups.

---

## Tool schemas and context window engineering

Claude Code's tool system comprises **16+ built-in tools** with carefully designed schemas. The core file operations demonstrate the safety-first approach:

| Tool | Key Parameters | Safety Mechanism |
|------|----------------|------------------|
| **Read** | `file_path`, `offset`, `limit` | Default 2000 lines, 2000 chars/line truncation |
| **Write** | `file_path`, `content` | Read-before-write enforcement—fails if existing file unread |
| **Edit** | `file_path`, `old_string`, `new_string` | Exact string matching, must be unique unless `replace_all` |
| **Bash** | `command`, `timeout` (max 600s) | 30,000 char output truncation, command sanitization |
| **Grep** | `pattern`, `path`, `output_mode` | Built on ripgrep, supports multiline and context |

The system prompt architecture is **modular and dynamic**, totaling approximately 2,972 tokens for the main prompt plus 11,600+ tokens for tool descriptions. Plan mode adds 633 tokens of constraint injection.

Context window management operates across **200K tokens standard** (500K enterprise, 1M beta), with the compactor automatically summarizing at ~95% capacity. The `/context` command reveals the breakdown: system prompt (1.6%), tools (5.8%), memory files (0.4%), leaving roughly 91% for conversation. Claude 4.5 models receive explicit budget tracking:

```xml
<system_warning>Token usage: 35000/200000; 165000 remaining</system_warning>
```

Extended thinking uses keyword-based budget allocation: "think" triggers basic thinking, "think hard" for medium, "think harder" for higher, and "ultrathink" for maximum (up to **31,999 tokens**).

---

## Ralph-wiggum: autonomous iteration through stop hooks

The ralph-wiggum plugin implements what developer Geoffrey Huntley describes as "Ralph is a Bash loop"—a `while true` that repeatedly feeds Claude the same prompt, allowing it to iteratively improve work until completion. Named after the perpetually confused but never-stopping Simpsons character, it enables autonomous multi-hour coding sessions.

The technical implementation centers on Claude Code's **Stop hook** mechanism:

```
/ralph-loop "Task description" --max-iterations 20 --completion-promise "DONE"
```

When Claude attempts to exit, the hook script (`stop-hook.sh`) intercepts the stop event, checks completion criteria, and returns **exit code 2** to block stoppage and inject the original prompt back via stderr. Exit code 0 allows completion. The hook receives JSON input via stdin containing `session_id`, `transcript_path`, and critically, `stop_hook_active` (preventing infinite loops).

The self-referential feedback loop works because **the prompt doesn't change but the codebase does**. Each iteration, Claude sees the same instruction but reads updated files and git history from previous attempts, learning from its own output. State persists in a Markdown file tracking iteration count, completion promise string, and original prompt.

Real-world results demonstrate the pattern's power: the CURSED programming language compiler was built over three months using Ralph loops, and a Y Combinator hackathon team shipped six repositories overnight for $297 in API costs. However, the technique requires careful scope—ambiguous requirements won't converge, and security-sensitive code needs human review at each step.

---

## Mistral adaptation: Devstral for offline deployment

Mistral's Devstral Small 2 (24B parameters, **Apache 2.0 license**) emerges as the optimal choice for air-gapped deployments—it runs on a single RTX 4090 or Mac with 32GB RAM while achieving **72.2% on SWE-Bench Verified**, comparable to frontier models. The 256K context window matches Claude's capabilities.

The critical architectural patterns that transfer cleanly to Mistral:

- **Single-threaded master loop**: Same while-loop architecture works identically
- **CLAUDE.md configuration pattern**: Create equivalent `AGENT.md` files for project context
- **Tool permission system**: Default-deny with explicit allowlists
- **Read-only parallel execution**: Classify tools by risk, parallelize only read operations

Mistral's function calling uses OpenAI-compatible JSON schemas:

```python
tools = [{
    "type": "function",
    "function": {
        "name": "execute_command",
        "description": "Execute a shell command",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"]
        }
    }
}]

response = client.chat.complete(
    model="devstral-small-latest",
    messages=messages,
    tools=tools,
    tool_choice="auto"
)
```

---

## Air-gapped deployment architecture

The reference architecture for secure offline deployment layers three critical components:

```
┌──────────────────────────────────────────────────────────┐
│                 AIR-GAPPED BOUNDARY                       │
├──────────────────────────────────────────────────────────┤
│  Agent Orchestration Layer (Claude Code patterns)        │
│    └── Master loop, tool routing, permission system      │
│                          │                                │
│  LLM Inference Service (vLLM recommended)                │
│    └── Devstral Small 2, tensor parallel, 131K context   │
│                          │                                │
│  Code Execution Sandbox (gVisor or Firecracker)          │
│    └── Hardware isolation, syscall filtering             │
└──────────────────────────────────────────────────────────┘
```

**vLLM deployment** provides production-grade performance with PagedAttention:

```bash
vllm serve /models/Devstral-Small-2-24B-Instruct \
  --tool-call-parser mistral \
  --enable-auto-tool-choice \
  --port 8080 \
  --max-model-len 131072
```

Model preparation for air-gap transfer requires downloading weights on a connected system (`huggingface-cli download`), packaging as tarball with SHA256 verification, physical transfer via approved media, and extraction on the isolated system with `HF_HUB_OFFLINE=1` environment variable.

Sandboxing hierarchy from strongest to lightest: **Firecracker microVMs** (125ms startup, used by AWS Lambda), **gVisor** (user-space kernel, recommended for Kubernetes), Docker with seccomp (minimum acceptable). For FedRAMP High compliance, implement 421 NIST SP 800-53 controls, FIPS 140-3 validated encryption, and comprehensive audit logging of all model interactions.

---

## LLM backend abstraction for model swappability

Building for future model upgrades requires an abstraction layer:

```python
class LLMBackend(ABC):
    @abstractmethod
    async def complete(self, messages, tools=None, **kwargs) -> Dict:
        pass
    
    @abstractmethod
    def supports_tool_calling(self) -> bool:
        pass
    
    @abstractmethod
    def get_context_limit(self) -> int:
        pass

class MistralBackend(LLMBackend):
    def __init__(self, endpoint: str, model: str = "devstral-small-2"):
        self.endpoint = endpoint
        self.model = model
    
    async def complete(self, messages, tools=None, **kwargs):
        payload = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return await self.client.post("/v1/chat/completions", json=payload)
```

Prompt adaptation between Claude and Mistral requires more explicit instruction formatting for Mistral models, XML format support (Devstral Small 1.1+), and different thinking triggers than Claude's "ultrathink" keyword.

---

## Security configuration for sensitive environments

A production configuration for government/corporate deployment:

```toml
[security]
sandbox_type = "gvisor"
require_approval = ["write_file", "execute_command", "git_push"]
blocked_tools = ["network_request", "external_api"]
audit_all_requests = true

[tools.file_operations]
allowed_paths = ["/workspace", "/home/developer/projects"]
blocked_patterns = ["*.env", "*.key", "*secrets*"]

[tools.shell]
allowed_commands = ["git", "npm", "python", "pytest", "cargo", "make"]
blocked_commands = ["curl", "wget", "nc", "ssh"]
max_execution_time = 300
```

The permission system should classify tools by risk level (LOW for read operations, MEDIUM for file writes, HIGH for command execution, BLOCKED for network access), log all requests regardless of approval status, and require elevated permissions for HIGH-risk operations.

---

## Conclusion

Claude Code's architecture succeeds through disciplined simplicity—a single-threaded loop with flat message history, prompt-based constraints rather than hard-coded restrictions, and file-based state management. Plan mode exemplifies this philosophy: the same tools remain available, but behavioral constraints redirect them toward research rather than modification.

For offline Mistral deployment, the key insight is that **these patterns are fundamentally model-agnostic**. The master loop, permission system, TODO-based planning, and checkpoint mechanisms all transfer directly. Mistral-specific adaptations focus on tool schema formatting, prompt engineering style, and inference server configuration rather than architectural changes.

The ralph-wiggum plugin demonstrates how Claude Code's hook system enables powerful extensions—autonomous iteration loops that would be dangerous without proper safeguards become viable with stop-hook interception and completion criteria. This pattern could enable overnight batch operations in secure environments where human oversight occurs at loop boundaries rather than every step.

For government deployments, prioritize Devstral Small 2 for its Apache 2.0 license and single-GPU feasibility, implement Firecracker or gVisor sandboxing, and build comprehensive audit logging from day one. The abstraction layer ensures future model upgrades require only backend implementation changes, not architectural rewrites.