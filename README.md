# Development Harness

**The open-source control plane for coding agents.**

Development Harness makes [Claude Code](https://docs.anthropic.com/en/docs/claude-code), [OpenAI Codex](https://openai.com/index/openai-codex/), and other coding agents reliable over long horizons. It does not replace your agent -- it wraps it with the scaffolding, feedback loops, verification, observability, and safety controls that turn a one-shot prompt into a production-grade workflow.

**Agent = Model + Harness.** The model is the intelligence. The harness is everything else.

This project is inspired by OpenAI's [Harness Engineering](https://openai.com/index/harness-engineering/) approach, where their team built and shipped a million lines of production code using only Codex agents -- and discovered that the bottleneck was never model capability, but **environment design**. The tools, the constraints, the feedback loops, the verification, the context architecture -- that is what makes agents actually work. This project is an open-source implementation of those principles, built to work with any agent backend.

```
pip install devharness
```

---

## Why a Harness?

If you have used Claude Code or Codex for non-trivial tasks, you have experienced this: the agent writes code, but you spend your day babysitting it. You are clicking approve on every tool call. You are manually running tests to check if the fix actually worked. You are copying error messages back into the chat. You are clicking buttons in the browser to see if the UI change looks right. You are losing context in long sessions.

The harness eliminates all of that:

- **The agent writes code** -- the harness automatically runs your tests, linter, and type checker and tells the agent what failed
- **The agent changes your UI** -- the harness launches a browser, clicks through the flow, captures screenshots, and tells the agent if the button actually works
- **The agent needs approval** -- you get a Slack message with approve/deny buttons, or click a button in the web UI, instead of watching a terminal
- **The agent hits an error it has seen before** -- the harness queries its knowledge graph and injects the previous fix into context
- **You come back after lunch** -- the harness persisted everything, checkpointed the session, and the agent can resume exactly where it left off

The harness is the engineering you would build if you were running agents in production. We built it so you do not have to.

---

## Features

### Agent Backends

The harness wraps your agent as a subprocess. It does not call LLM APIs directly -- your agent (Claude Code, Codex) handles its own conversation, tool calls, and reasoning. The harness manages the session around it: what context to inject, what policies to enforce, what to verify afterward, and what to do when things break.

- **Claude Code** -- spawned with `--output-format stream-json`, harness parses streaming events, injects context via prompt, enforces tool policies via `--allowedTools`/`--disallowedTools`
- **Codex** -- same pattern via the `codex` CLI with `--approval-mode` mapping
- **Sub-agent pool** -- spawn lightweight agents for discrete subtasks with isolated context windows (context firewall pattern). The parent agent stays focused; sub-agents handle research, search, and analysis with cheaper models
- **Add your own** -- implement one abstract class (`AgentBackend`) with three methods

### Codebase Onboarding

Run `harness init` in any existing project. The harness scans your codebase and automatically configures itself:

```bash
cd your-project
harness init
```

```
Scanning codebase...

Detected:
  Language:    python
  Frameworks:  fastapi, sqlalchemy, pydantic
  Tests:       pytest
  Package mgr: pip
  Project type: API
  Size:        medium

  Created AGENTS.md with project-specific instructions
  Generated 4 hook scripts in .devharness/hooks/
  Stored 6 settings in database
```

The scanner detects **40+ languages**, package managers (pip, npm, cargo, go mod, etc.), frameworks (Django, FastAPI, React, Next.js, Express, etc.), test runners (pytest, jest, vitest, go test, etc.), CI systems (GitHub Actions, GitLab CI, etc.), Docker, Makefiles, and more. It generates:

- **AGENTS.md** -- project-specific context file with directory structure, commands, conventions, and framework-specific instructions
- **Hook scripts** -- format, lint, typecheck, and test hooks configured for your detected tooling
- **Database settings** -- observer config, skill selection, and defaults stored in SQLite

You go from `git clone` to a fully configured harness in one command.

### Hooks System

Hooks are shell scripts triggered at agent lifecycle events. They are the harness's deterministic control flow -- no LLM reasoning involved. The critical convention:

- **Exit 0** = success. Output is **swallowed** (no context pollution -- 4000 lines of passing tests would flood the agent's context window)
- **Exit 2** = re-engage. The script's stdout is **injected into the agent's context** as corrective feedback
- **Other exit codes** = warning logged, execution continues

```
┌─────────────┐    ┌──────────────┐    ┌──────────────────────────┐
│ Agent writes │───▶│ post_tool    │───▶│ exit 0: silent (tests    │
│ code         │    │ hook runs    │    │         pass, move on)   │
│              │    │ pytest       │    │                          │
│              │    │              │    │ exit 2: "3 tests failed: │
│              │    │              │    │  test_login: expected    │
│              │    │              │    │  302 got 404"            │
│              │    │              │    │  → injected into agent   │
│              │    │              │    │    context, agent fixes  │
└──────────────┘    └──────────────┘    └──────────────────────────┘
```

Hook events: `pre_turn`, `post_turn`, `pre_tool_call`, `post_tool_call`, `pre_commit`, `post_commit`, `on_error`, `on_idle`

This is how the OpenAI team achieved "silent success, failures surfaced" -- the same pattern that let them process a billion tokens per day without drowning agents in irrelevant output.

### Tiered Context Architecture

Most agent failures come from context window mismanagement. A giant instruction file causes the agent to ignore rules. Too much conversation history causes hallucination. The harness uses three tiers with a **40% utilization target** (empirically shown to be the sweet spot):

| Tier | What | When Loaded | Budget |
|------|------|-------------|--------|
| **Hot** | System prompt, project constitution (AGENTS.md), active skill prompts | Always | ~5-10% |
| **Warm** | Task instructions, relevant docs, recent turn summaries, observation reports | Per-task | ~15-25% |
| **Cold** | Full codebase search, knowledge base queries, external docs | On-demand via tools | Remaining |

When everything is described as important, the agent stops following rules. The tiered system keeps Tier 1 concise (~60 lines) and loads detail only when needed.

### Observer Pipeline

Eight concurrent observers watch your application and produce structured feedback that gets injected into the agent's context. The agent sees what its changes actually caused.

| Observer | What It Watches | What the Agent Sees |
|----------|----------------|---------------------|
| **Process** | Dev servers, background processes | "Flask server crashed with ImportError on models.py:42" |
| **Log** | Application log files | "3 new ERROR entries since your last change" |
| **Test** | Test suite output (pytest, jest, etc.) | "test_login_redirect FAILED: expected 302, got 404 at auth/views.py:87" |
| **Endpoint** | HTTP endpoint health probes | "POST /api/auth returns 500: KeyError 'token'" |
| **Lint** | Linter output (ruff, eslint, etc.) | "2 new warnings in auth/views.py: unused import, line too long" |
| **Build** | Compilation / type checker | "mypy: auth/models.py:42 - Argument 1 has incompatible type" |
| **Metrics** | CPU, memory, response times | "avg API latency increased from 45ms to 230ms" |
| **Browser** | UI interactions via Playwright | "Login button click → TypeError in console; screenshot attached" |

The observation summary follows the "success silent, failures only" principle. If all tests pass and all endpoints are healthy, the agent gets a one-line "no issues detected" instead of 4000 lines of green output.

### Browser Testing

This is the feature that replaces you clicking buttons all day. Browser tests are **fused into the verification loop** -- not a separate step you run manually.

Define interaction flows in YAML:

```yaml
# .devharness/browser_tests/login_flow.yaml
name: login_flow
url: http://localhost:3000/login
steps:
  - action: fill
    selector: "input[name='email']"
    value: "test@example.com"
  - action: fill
    selector: "input[name='password']"
    value: "testpass123"
  - action: click
    selector: "button[type='submit']"
  - action: wait_for
    selector: ".dashboard"
    timeout: 5000
  - action: screenshot
    name: "after_login"
assertions:
  - type: url_contains
    value: "/dashboard"
  - type: element_visible
    selector: ".welcome-message"
  - type: no_console_errors
```

What happens when the agent changes UI code:

1. Post-tool hook detects UI files changed
2. Browser observer launches headless Playwright
3. Executes the interaction flow step by step
4. Captures **screenshots** as artifacts (viewable in web UI and Slack)
5. Captures **console errors** (zero tolerance for uncaught exceptions)
6. Rasterizes the **DOM to text** for the agent's context
7. Agent sees: *"After clicking Submit, console shows: TypeError: Cannot read property 'email' of undefined at UserForm.jsx:42"*
8. Agent self-corrects

The agent tests its own UI changes. You stop clicking buttons.

### Verification and Repair Loop

After each agent turn, the harness runs a verification pipeline. If verification fails, the harness **automatically re-delegates** with the failure context -- the agent gets a structured list of what broke and tries to fix it (up to 2 repair attempts).

```
Agent completes work
        │
        ▼
┌─────────────────┐    ┌──────────────┐
│ Verification    │───▶│ All passed?  │──yes──▶ Checkpoint & done
│ Pipeline runs:  │    │              │
│ - tests         │    │  No:         │
│ - lint          │    │  attempt < 2 │──yes──▶ Re-delegate with
│ - format        │    │              │         failure context
│ - type check    │    │  No:         │
│ - schema        │    │  max retries │──▶ Report failures
│ - file exists   │    └──────────────┘
│ - browser flows │
└─────────────────┘
```

Seven built-in verifiers: **test** (pytest), **lint** (ruff), **format** (ruff format), **type check** (mypy), **schema** (JSON/YAML validation), **file existence** (required files), **browser** (Playwright flows). Add custom verifiers by implementing one abstract method.

### Approval Policies

Five modes from full autonomy to complete lockdown:

| Mode | Reads | Writes | Executes | Best For |
|------|-------|--------|----------|----------|
| `full_trust` | auto | auto | auto | Trusted CI environments |
| `auto_approve_safe` | auto | **approve** | **approve** | Default -- safe exploration |
| `workspace_write` | auto | auto (in workspace) | **approve** | Active development |
| `approval_required` | **approve** | **approve** | **approve** | Sensitive codebases |
| `read_only` | auto | **deny** | **deny** | Code review, investigation |

Plus custom policy rules:
- **DenyPathPattern** -- block writes to `.env`, `credentials*`, `secrets/`
- **DenyCommand** -- block `rm -rf /`, `sudo`, `curl | bash`
- **MaxFileSize** -- block writes exceeding size threshold

Approvals can be resolved from the **CLI**, **web UI**, or **Slack**.

### Skills System

Skills are reusable capability packs that bundle a system prompt, tool set, and verifier set. Loaded from directories with `manifest.yaml` + `prompt.md`.

```
skills/coding_general/
  manifest.yaml     # name, tools, verifiers
  prompt.md          # system prompt (20-40 lines of focused instructions)
```

Seven built-in skills:

| Skill | Purpose |
|-------|---------|
| `coding/general` | General-purpose coding assistance |
| `coding/reviewer` | Code review with structured feedback |
| `docs/writer` | Documentation generation |
| `sre/investigator` | Incident investigation and debugging |
| `repo/maintainer` | Repository maintenance and cleanup |
| `test/fixer` | Fix failing tests |
| `codebase/onboarding` | Learn a new codebase and produce architecture summary |

Create your own skill in 2 files. The system prompt stays concise -- the agent gets skill context in Tier 2 (warm), not crammed into the system prompt.

### Slack Integration

Socket Mode (outbound WebSocket only). No webhooks, no exposed ports, no network exposure. Works from your phone while you are away from your desk.

- **Approve/deny** pending tool calls with buttons
- **Submit tasks** via `/harness run fix the login page`
- **Check status** via `/harness status`
- **Get notifications** when threads complete, fail, or need attention
- **Receive screenshots** from browser test failures as image attachments

### Knowledge Graph Memory

Two pluggable memory backends for persistent project knowledge:

**Neo4j** (for power users) -- graph-based knowledge layer with 30+ node types, 30+ relationship types, native vector indexes, and GraphRAG retrieval. Daily consolidation summarizes raw events into decisions, concepts, and patterns. Agents query with three tools: `memory_query` (structured Cypher), `memory_search` (vector similarity), `memory_traverse` (graph walk).

**Obsidian Vault** (zero infrastructure) -- Markdown files with YAML frontmatter in a project folder. Human-readable, git-friendly, browseable in the Obsidian app. Architecture decisions, session summaries, error patterns, and concepts are all plain text files with wiki-style `[[links]]`.

Both are optional. The harness works without any memory backend. Memory is enhancement, not dependency -- if Neo4j goes down, events are buffered in SQLite and replayed when it comes back.

### Task DAG

Decompose complex tasks into dependency graphs and execute them in parallel with sub-agents:

```python
Task: "Add authentication to the API"
  ├── [#1] Add JWT middleware          (no deps)
  ├── [#2] Create login endpoint       (blocked by #1)
  ├── [#3] Create signup endpoint      (blocked by #1)
  ├── [#4] Add auth to protected routes (blocked by #1)
  └── [#5] Write auth tests            (blocked by #2, #3, #4)
```

Tasks #1 runs first. Then #2, #3, #4 run in parallel (independent). Then #5 runs after all complete. Each task gets its own sub-agent with isolated context.

### Web UI

A lightweight dashboard built with Starlette + HTMX + Pico CSS. No JavaScript build step, no React, no webpack. Server-rendered with real-time updates via SSE.

| Page | What You See |
|------|-------------|
| **Dashboard** | All threads with status badges, project stats |
| **Thread Detail** | Live event stream, tool call history, artifacts, approval actions |
| **Approvals** | Pending approval cards with approve/deny buttons |
| **Observe** | Process status, test results, endpoint health, error feed |
| **Skills** | Browse available skills and their manifests |
| **Settings** | Configure everything -- approval modes, integrations, memory |

### DB-First Configuration

No YAML config files. No `.env` files. No API keys in source code.

Claude Code and Codex manage their own authentication -- the harness never touches LLM API keys. The only credentials the harness stores are for its own integrations (Slack, Neo4j, embedding model).

The only environment variable is `DEVHARNESS_STORAGE_DIR` (default: `.devharness`). Everything else lives in the SQLite database, configurable from the CLI, web UI, or by the agent itself:

```bash
harness config list                                    # see all settings
harness config set server.port 9000                    # change a setting
harness config set default.approval_mode full_trust    # change default mode
harness config set-credential slack.bot_token xoxb-... # store Slack token
harness config get default.approval_mode               # read a setting
```

The agent can run `harness config set` to manage its own configuration. No human needed for config management.

### Mechanical Enforcement

Custom linter integration where violation messages include **agent-readable correction prompts**. When the agent violates an architectural rule, the enforcement engine tells it exactly how to fix it:

```
Import violation: auth/views.py imports from ui/components.py
Architecture: Types → Config → Repo → Service → Runtime → UI
Fix: auth/ is in the Service layer. It must not import from UI.
Move the shared code to a lower layer or use dependency injection.
```

This is the pattern the OpenAI team used for dependency layer enforcement -- mechanical rules that catch violations immediately and inject correction instructions directly into the agent's context.

---

## Quick Start

### Install

```bash
pip install devharness          # core
pip install devharness[all]     # everything
pip install devharness[server]  # web UI only
pip install devharness[browser] # Playwright testing
pip install devharness[slack]   # Slack integration
```

### Initialize in your project

```bash
cd your-project
harness init                    # scans codebase, generates config
```

### Run your first task

No API keys needed -- Claude Code and Codex handle their own auth.

```bash
harness run "fix the failing tests"
```

### Start the web UI

```bash
harness serve
# => http://127.0.0.1:8390
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `harness init` | Scan codebase and initialize harness configuration |
| `harness run <prompt>` | Run a prompt in a new thread |
| `harness serve` | Start the web UI and API server |
| `harness threads` | List threads (`--project`, `--status` filters) |
| `harness replay <thread_id>` | Replay events from a completed thread |
| `harness approve <thread_id> <approval_id>` | Approve or deny (`--approve`/`--deny`) |
| `harness skills` | List available skills |
| `harness artifacts <thread_id>` | List artifacts for a thread |
| `harness config list` | List all configurable settings |
| `harness config get <key>` | Read a setting value |
| `harness config set <key> <value>` | Set a setting |
| `harness config set-credential <key> <value>` | Store a credential securely |

---

## Documentation

| Doc | What You Learn |
|-----|---------------|
| [Training Guide](docs/training.md) | Complete walkthrough of every system -- start here |
| [Architecture](docs/architecture.md) | Module map, data flow, design decisions |
| [Protocol](docs/protocol.md) | JSON-RPC methods and event types |
| [Safety](docs/safety.md) | Approval modes and policy rules |
| [Skills](docs/skills.md) | Creating and managing skills |
| [Tools](docs/tools.md) | Built-in tools and custom tool creation |
| [Hooks](docs/hooks.md) | Lifecycle hooks and the exit code contract |
| [Observability](docs/observability.md) | Observer pipeline and monitoring |
| [Browser Testing](docs/browser-testing.md) | Playwright-based frontend testing |
| [Neo4j Memory](docs/neo4j-memory.md) | Graph-based knowledge architecture |
| [Contributing](docs/contributing.md) | Development setup and PR process |

---

## Inspiration

This project implements the principles described in OpenAI's [Harness Engineering: Leveraging Codex in an Agent-First World](https://openai.com/index/harness-engineering/), where a small team built and shipped a beta product containing roughly a million lines of code without any manually written source code -- processing approximately a billion tokens per day. Their key finding: **the bottleneck in agent performance is often not model intelligence, but environment design.**

The harness engineering approach shifts the developer's role from writing code to designing environments, specifying intent, and building feedback loops. This project makes those patterns available as open-source infrastructure.

Key principles borrowed from the research:

- **Scaffolding over raw prompting** -- the harness matters more than the prompt
- **Silent success, surfaced failures** -- hooks swallow passing output, inject failures
- **Tiered context disclosure** -- give the agent a map, not a 1000-page manual
- **Mechanical enforcement** -- linter errors with self-correction instructions
- **Verification loops** -- plan → act → observe → verify → repair
- **Disposable execution** -- fork/retry on persistent failures
- **Context firewalls** -- sub-agents with isolated context prevent rot

---

## Contributing

See [docs/contributing.md](docs/contributing.md) for the full guide.

```bash
git clone https://github.com/ColtMercer/Development-Harness.git
cd Development-Harness
pip install -e ".[dev,all]"
pytest                          # 129 tests, <1 second
```

## License

MIT. See [LICENSE](LICENSE).
