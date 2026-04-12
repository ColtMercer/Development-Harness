# Development Harness

**Control plane for long-running coding and ops agents.**

Development Harness is an open-source Python framework that wraps [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and [OpenAI Codex](https://openai.com/index/openai-codex/) as pluggable backends. It does not implement its own LLM loop. Instead, it provides the environment -- scaffolding, constraints, feedback loops, context architecture, verification, observability, and recovery -- that makes agents reliable over long horizons.

The core thesis: **Agent = Model + Harness**, and the harness is everything except the model.

```
pip install devharness
```

## Key Features

- **Pluggable Agent Backends** -- Claude Code and Codex run as subprocesses with a unified streaming interface. Add new backends by implementing one abstract class.
- **Lifecycle Hooks** -- Scripts triggered at agent lifecycle events (pre/post turn, pre/post tool call, pre/post commit). Success is silent; exit code 2 re-engages the agent with corrective context.
- **Tiered Context Architecture** -- Three-tier system (hot/warm/cold) targeting 40% context utilization. Keeps the model focused without overwhelming the context window.
- **Observer Pipeline** -- Concurrent observers monitor process health, test results, lint output, build status, log tails, endpoint health, and browser state. Findings are injected into agent context.
- **Browser Testing** -- Playwright-based interaction flows defined in YAML. Screenshots, DOM snapshots, and console errors are captured and fed back to the agent for self-correction.
- **Verification and Repair** -- Post-turn verification pipeline with automatic repair attempts. If verification fails, the harness re-delegates with failure context.
- **Approval Policies** -- Five approval modes from full trust to read-only, plus custom policy rules that block dangerous commands and sensitive file paths.
- **Skills System** -- Composable skill packs that bundle system prompts, tool sets, and verifiers. Loaded from directories with `manifest.yaml` + `prompt.md`.
- **Task DAG** -- Dependency graph for parallel task execution with sub-agent context firewalls.
- **Slack Integration** -- Socket Mode (outbound only, no webhooks). Approve/deny from Slack, receive notifications, submit tasks.
- **Neo4j Memory** -- Optional graph-based knowledge layer with vector search, daily consolidation, and GraphRAG retrieval.
- **Obsidian Vault** -- Alternative file-based memory backend using Markdown with YAML frontmatter. Git-friendly, human-readable.
- **Web UI** -- HTMX + SSE dashboard for thread management, observation monitoring, and configuration.
- **SQLite Storage** -- All state in a single file. No config files in source code. Credentials stored in the database, not YAML.

## Architecture

```
+----------------------------------------------------------------------+
|                        Development Harness                            |
|                                                                       |
|  +-----------+  +-----------+  +-----------+  +-----------+           |
|  |  Context  |  | Feedfwd   |  | Feedback  |  |   Hooks   |           |
|  |  Arch.    |  | Controls  |  | Controls  |  |  System   |           |
|  | (tiered   |  | (guides,  |  | (tests,   |  | (lifecycle|           |
|  |  loading) |  |  linters) |  |  observe) |  |  scripts) |           |
|  +-----+-----+  +-----+-----+  +-----+-----+  +----+-----+           |
|        |              |              |              |                  |
|  +-----v--------------v--------------v--------------v---------+       |
|  |                 Runtime Orchestrator                        |       |
|  |  hooks -> context -> delegate -> observe -> verify ->      |       |
|  |  repair -> hooks -> checkpoint -> summarize                |       |
|  +--------------------------+-----------------------------+---+       |
|                             |                             |           |
|  +--------------------------v----+  +---------------------v------+    |
|  |      Agent Backend Interface  |  |      Sub-Agent Pool        |    |
|  |  +----------+  +-----------+  |  |  (isolated context         |    |
|  |  |Claude    |  |  Codex    |  |  |   firewalls, semaphore)    |    |
|  |  |Code      |  |  Backend  |  |  +----------------------------+    |
|  |  |(subproc) |  | (subproc) |  |                                    |
|  |  +----------+  +-----------+  |                                    |
|  +-------------------------------+                                    |
|                                                                       |
|  +--------+ +-------+ +------+ +---------+ +------+ +---------+      |
|  | Skills | | Tools | | Task | |Artifacts| |Memory| | Web UI  |      |
|  | System | | Reg.  | |  DAG | | Manager | |Service| |(HTMX)  |      |
|  +--------+ +-------+ +------+ +---------+ +------+ +---------+      |
+-----------------------------------------------------------------------+
```

## Quick Start

### Install

```bash
# Core
pip install devharness

# With all optional features
pip install devharness[all]

# Individual extras
pip install devharness[server]        # Web UI
pip install devharness[browser]       # Playwright browser testing
pip install devharness[slack]         # Slack integration
pip install devharness[memory-neo4j]  # Neo4j knowledge graph
pip install devharness[observers]     # Process/system observers
```

### Initialize a project

```bash
cd your-project
harness init
```

This creates a `.devharness/` directory with a SQLite database. The directory is automatically added to `.gitignore`.

### Run a prompt

```bash
harness run "fix the failing tests in src/auth/"
```

Options:

```bash
harness run "add rate limiting" --agent codex
harness run "refactor the User model" --skill python-web --approval-mode full_trust
harness run "fix login page" --project my-webapp
```

### Start the web UI

```bash
harness serve
# => http://127.0.0.1:8390
```

```bash
harness serve --host 0.0.0.0 --port 9000
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `harness init` | Initialize project harness configuration |
| `harness run <prompt>` | Run a prompt in a new thread |
| `harness serve` | Start the harness server with web UI |
| `harness threads` | List threads (optional `--project`, `--status` filters) |
| `harness replay <thread_id>` | Replay events from a thread |
| `harness approve <thread_id> <approval_id>` | Approve or deny a pending request (`--approve`/`--deny`) |
| `harness skills` | List available skills |
| `harness artifacts <thread_id>` | List artifacts for a thread |

### Global Options

| Option | Description |
|--------|-------------|
| `--storage-dir <path>` | Override storage directory (default: `.devharness/`) |
| `--log-level <level>` | Set log level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

## Configuration

**DB-first design**: All configuration lives in the SQLite database. No YAML config files, no API keys in source code. The agent can manage its own config.

The only environment variable is `DEVHARNESS_STORAGE_DIR` (default: `.devharness`), which tells the harness where to find its database. Everything else is stored in the DB and configurable from the CLI, web UI, or by the agent itself.

### Managing Config

```bash
# List all configurable settings
harness config list

# Set a setting
harness config set server.port 9000
harness config set default.agent_backend codex
harness config set default.approval_mode full_trust
harness config set log.level DEBUG

# Store credentials (never in source code)
harness config set-credential anthropic.api_key sk-ant-...
harness config set-credential openai.api_key sk-...
harness config set-credential slack.bot_token xoxb-...

# Read a setting
harness config get server.port
harness config get anthropic.api_key   # shows masked value
```

### Available Settings

| Key | Default | Description |
|-----|---------|-------------|
| `server.host` | `127.0.0.1` | Server bind address |
| `server.port` | `8390` | Server port |
| `default.approval_mode` | `auto_approve_safe` | Default approval mode |
| `default.agent_backend` | `claude-code` | Default agent backend |
| `default.memory_backend` | `none` | Memory backend (`none`, `neo4j`, `obsidian`) |
| `log.level` | `INFO` | Logging level |
| `neo4j.uri` | `bolt://localhost:7687` | Neo4j connection URI |
| `neo4j.enabled` | `false` | Enable Neo4j memory |

### Credentials (stored securely in DB)

| Key | Description |
|-----|-------------|
| `anthropic.api_key` | Anthropic API key (for Claude Code) |
| `openai.api_key` | OpenAI API key (for Codex) |
| `neo4j.password` | Neo4j password |
| `slack.app_token` | Slack app token (xapp-...) |
| `slack.bot_token` | Slack bot token (xoxb-...) |

### Approval Modes

| Mode | Behavior |
|------|----------|
| `full_trust` | All tool calls auto-approved |
| `auto_approve_safe` | Read tools auto-approved; write/execute require approval |
| `approval_required` | Every tool call requires explicit approval |
| `read_only` | Only read tools allowed; write/execute denied |
| `workspace_write` | Read and write auto-approved; execute requires approval |

## Project Structure

```
.devharness/
  harness.db          # SQLite database (all config, state, events)
  artifacts/          # Binary artifacts (screenshots, patches)
  .gitignore          # Auto-generated, ignores everything
```

```
skills/
  my-skill/
    manifest.yaml     # Skill metadata
    prompt.md         # System prompt for this skill
```

```
.devharness/hooks/
  format_check.json   # Hook configuration files
  test.json
```

```
.devharness/browser_tests/
  login_flow.yaml     # Browser interaction flows
  checkout.yaml
```

## Documentation

- [Training Guide](docs/training.md) -- Comprehensive walkthrough of every system
- [Architecture](docs/architecture.md) -- Module map, data flow, design decisions
- [Protocol Reference](docs/protocol.md) -- JSON-RPC methods and event types
- [Safety and Approvals](docs/safety.md) -- Approval modes and policy rules
- [Skills System](docs/skills.md) -- Creating and managing skills
- [Tools System](docs/tools.md) -- Built-in tools and custom tool creation
- [Hooks System](docs/hooks.md) -- Lifecycle hooks and exit code semantics
- [Observability](docs/observability.md) -- Observer pipeline and monitoring
- [Browser Testing](docs/browser-testing.md) -- Playwright-based frontend testing
- [Neo4j Memory](docs/neo4j-memory.md) -- Graph-based knowledge architecture
- [Contributing](docs/contributing.md) -- Development setup and PR process

## Contributing

See [docs/contributing.md](docs/contributing.md) for the full contributor guide.

```bash
git clone https://github.com/ColtMercer/Development-Harness.git
cd Development-Harness
pip install -e ".[dev,all]"
pytest
```

## License

MIT. See [LICENSE](LICENSE) for details.
