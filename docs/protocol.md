# Protocol Reference

This document describes the event types, request/response formats, and JSON-RPC methods used by the Development Harness.

---

## Event Types

Every significant action in the harness emits an `Event` via the event bus. Events are persisted to SQLite and streamed to subscribers (web UI via SSE, Slack, storage).

### Event Structure

```json
{
    "id": "a1b2c3d4e5f6",
    "thread_id": "f6e5d4c3b2a1",
    "turn_id": "123456789abc",
    "kind": "turn.start",
    "timestamp": "2026-04-12T14:30:00.000Z",
    "data": {}
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique event identifier (12-char hex) |
| `thread_id` | string | Thread this event belongs to |
| `turn_id` | string or null | Turn this event belongs to (null for thread-level events) |
| `kind` | string | Event kind (see table below) |
| `timestamp` | ISO 8601 | UTC timestamp |
| `data` | object | Event-specific payload |

### Event Kinds

#### Thread Lifecycle

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `thread.created` | Thread is created | |
| `thread.started` | Thread execution begins | |
| `thread.paused` | Thread paused for approval | `approval_id` |
| `thread.resumed` | Thread resumed after approval | |
| `thread.completed` | Thread finishes successfully | |
| `thread.failed` | Thread fails with error | `error` |
| `thread.cancelled` | Thread is cancelled | |

#### Turn Lifecycle

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `turn.start` | Turn begins | |
| `turn.end` | Turn ends | |

#### Agent Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `agent.started` | Agent subprocess launched | |
| `agent.output` | Agent produces output | `type`, `content`, `subtype` (for text); `tool_name`, `arguments` (for tool calls) |
| `agent.completed` | Agent finishes | |
| `agent.error` | Agent encounters error | `error` |

#### Tool Call Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `tool_call.start` | Tool execution begins | `tool_name`, `arguments` |
| `tool_call.end` | Tool execution ends | `tool_name`, `output`, `is_error`, `duration_ms` |

#### Approval Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `approval.requested` | Tool call requires approval | `approval_id`, `tool_name`, `arguments`, `category`, `reason` |
| `approval.resolved` | Approval granted or denied | `approval_id`, `approved`, `reason` |

#### Verification Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `verification.start` | Verification pipeline starts | |
| `verification.end` | Verification pipeline ends | `all_passed`, `results` |

#### Observation Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `observation` | Observer produces a finding | `observer_name`, `severity`, `title`, `details` |
| `browser_test.passed` | Browser test flow passes | `flow_name`, `steps_completed`, `duration_ms` |
| `browser_test.failed` | Browser test flow fails | `flow_name`, `failure_step`, `failure_reason`, `console_errors` |

#### Hook Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `hook.start` | Hook script begins | `hook_name`, `event` |
| `hook.end` | Hook script ends | `hook_name`, `exit_code`, `duration_ms` |
| `hook.reengage` | Hook exits with code 2 | `hook_name`, `stdout` |

#### Artifact Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `artifact.created` | Artifact is saved | `artifact_id`, `kind`, `name` |

#### Checkpoint Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `checkpoint.saved` | Thread state checkpointed | |

#### Error Events

| Kind | Emitted When | Data Fields |
|------|-------------|-------------|
| `error` | Unhandled error | `error`, `traceback` |

---

## Agent Event Protocol

Agent backends emit `AgentEvent` objects parsed from their streaming JSON output. These are internal events within a turn, distinct from the harness-level `Event` objects.

### AgentEvent Structure

```json
{
    "type": "text",
    "data": {
        "content": "I'll fix the failing test..."
    },
    "timestamp": "2026-04-12T14:30:01.000Z"
}
```

### AgentEvent Types

| Type | Description | Data Fields |
|------|-------------|-------------|
| `text` | Text output from the agent | `content`, `subtype` |
| `tool_call` | Agent is calling a tool | `tool_name`, `tool_call_id`, `arguments` |
| `tool_result` | Tool returned a result | `tool_call_id`, `output`, `is_error` |
| `done` | Agent finished | `content`, `cost`, `duration_ms`, `token_usage` |
| `error` | Agent error | `message` |

### Claude Code Stream Format

Claude Code emits newline-delimited JSON via `--output-format stream-json`. The harness parser (`parse_claude_code_event`) maps:

| Claude Code Type | AgentEvent Type |
|-----------------|-----------------|
| `assistant` / `text` | `text` |
| `tool_use` | `tool_call` |
| `tool_result` | `tool_result` |
| `result` | `done` |
| `error` | `error` |
| `system` / `ping` / `progress` / `start` | Ignored |

### Codex Stream Format

Codex emits a similar newline-delimited JSON stream. The parser (`parse_codex_event`) maps:

| Codex Type | AgentEvent Type |
|-----------|-----------------|
| `message` | `text` |
| `function_call` / `tool_call` | `tool_call` |
| `function_return` / `tool_return` | `tool_result` |
| `completed` | `done` |
| `error` | `error` |
| `status` / `ping` / `init` | Ignored |

---

## HTTP API

The harness server exposes a REST API via Starlette when running with `harness serve`.

### Threads

#### Create Thread

```
POST /api/threads
Content-Type: application/json

{
    "agent_backend": "claude-code",
    "approval_mode": "auto_approve_safe",
    "workspace_root": "/path/to/project",
    "skills": ["python-web"],
    "max_turns": 50
}
```

Response:

```json
{
    "id": "a1b2c3d4e5f6",
    "status": "pending",
    "config": { ... },
    "created_at": "2026-04-12T14:30:00.000Z"
}
```

#### Run Turn

```
POST /api/threads/{thread_id}/turns
Content-Type: application/json

{
    "user_input": "Fix the failing tests"
}
```

Response: Turn object with `assistant_response`, `tool_calls`, `verification`, etc.

#### List Threads

```
GET /api/threads
GET /api/threads?project_id=abc123&status=running
```

#### Get Thread

```
GET /api/threads/{thread_id}
```

#### Cancel Thread

```
POST /api/threads/{thread_id}/cancel
```

### Approvals

#### Resolve Approval

```
POST /api/threads/{thread_id}/approvals/{approval_id}
Content-Type: application/json

{
    "approved": true,
    "reason": "Looks safe"
}
```

### Events

#### Stream Events (SSE)

```
GET /api/threads/{thread_id}/events/stream
Accept: text/event-stream
```

Server-Sent Events stream. Each event is a JSON object.

#### List Events

```
GET /api/threads/{thread_id}/events
```

### Artifacts

#### List Artifacts

```
GET /api/threads/{thread_id}/artifacts
```

#### Get Artifact

```
GET /api/artifacts/{artifact_id}
```

### Skills

#### List Skills

```
GET /api/skills
```

---

## Domain Model JSON Schemas

### Thread

```json
{
    "id": "a1b2c3d4e5f6",
    "project_id": "proj123",
    "status": "running",
    "config": {
        "project_id": "proj123",
        "agent_backend": "claude-code",
        "approval_mode": "auto_approve_safe",
        "workspace_root": "/path/to/project",
        "allowed_tools": null,
        "denied_tools": null,
        "skills": ["python-web"],
        "max_turns": 50,
        "max_tool_calls_per_turn": 100,
        "verification_enabled": true,
        "context_window": 200000,
        "system_prompt_override": null
    },
    "turns": [],
    "metadata": {},
    "created_at": "2026-04-12T14:30:00.000Z",
    "updated_at": "2026-04-12T14:30:00.000Z",
    "current_turn_id": null,
    "pending_approval": null
}
```

### Turn

```json
{
    "id": "turn123",
    "thread_id": "a1b2c3d4e5f6",
    "user_input": "Fix the failing tests",
    "plan": null,
    "tool_calls": [],
    "events": [],
    "verification": {
        "id": "ver123",
        "thread_id": "a1b2c3d4e5f6",
        "turn_id": "turn123",
        "results": [
            {
                "verifier_name": "pytest",
                "passed": true,
                "message": "All tests passed",
                "details": {},
                "duration_ms": 2340.5
            }
        ],
        "all_passed": true,
        "created_at": "2026-04-12T14:31:00.000Z"
    },
    "artifacts": [],
    "assistant_response": "I fixed the failing test by...",
    "started_at": "2026-04-12T14:30:00.000Z",
    "ended_at": "2026-04-12T14:31:00.000Z",
    "error": null
}
```

### ApprovalRequest

```json
{
    "id": "appr123",
    "tool_call_id": "tc456",
    "tool_name": "shell",
    "arguments": {"command": "rm -rf node_modules && npm install"},
    "category": "execute",
    "reason": "Execute tool requires approval in auto_approve_safe mode",
    "status": "pending",
    "decided_by": null,
    "decided_at": null,
    "denial_reason": null
}
```

### Observation

```json
{
    "id": "obs123",
    "observer_name": "test",
    "thread_id": "a1b2c3d4e5f6",
    "turn_id": "turn123",
    "severity": "error",
    "title": "3 tests failed",
    "details": "test_login: Expected 200, got 401\ntest_signup: timeout",
    "data": {
        "test_summary": {
            "total": 42,
            "passed": 39,
            "failed": 3,
            "errored": 0,
            "skipped": 0
        }
    },
    "timestamp": "2026-04-12T14:30:30.000Z",
    "source_file": null,
    "source_line": null
}
```

### BrowserTestResult

```json
{
    "flow_name": "login_flow",
    "passed": false,
    "steps_completed": 3,
    "steps_total": 5,
    "failure_step": 3,
    "failure_reason": "Element .dashboard not found after 5000ms timeout",
    "screenshots": ["artifact_abc123"],
    "console_errors": ["TypeError: Cannot read property 'email' of undefined"],
    "dom_snapshot": "Login Page Welcome back...",
    "duration_ms": 8240.0
}
```
