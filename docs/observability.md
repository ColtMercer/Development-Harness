# Observer System

The observer system is the harness's sensory pipeline. Observers watch aspects of the application under development -- process health, test results, lint output, build status, log files, HTTP endpoints, browser state, and application metrics -- and produce structured `Observation` objects that are injected into the agent's context.

---

## Design Principles

### Success Is Silent, Failures Are Highlighted

The observation summary follows the same principle as hooks. When everything is healthy, the agent receives a minimal "No issues detected" message. When something is wrong, the agent receives specific, actionable failure details. This keeps the agent focused on real problems.

### Concurrent Execution

All observers run concurrently via `anyio.create_task_group()`. A slow or failing observer does not block the others. Exceptions are caught per-observer and logged, never propagated.

### Structured Output

Observations are Pydantic models, not raw strings. They have severity levels (`info`, `warning`, `error`, `critical`), source attribution (`observer_name`), and structured data payloads. This enables filtering, aggregation, and programmatic consumption.

---

## Observer Interface

```python
from abc import ABC, abstractmethod
from devharness.core.models import Observation, Thread, Turn

class BaseObserver(ABC):
    name: str

    @abstractmethod
    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Run observation and return findings.
        Returns an empty list if nothing noteworthy was detected.
        """

    @abstractmethod
    async def start(self) -> None:
        """Start any continuous monitoring (e.g., process watching, log tailing)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop continuous monitoring and clean up resources."""

    @property
    def is_running(self) -> bool:
        """Whether continuous monitoring is active."""
        return False
```

### start() and stop()

Some observers run continuously in the background (tailing log files, polling process health). `start()` and `stop()` manage this lifecycle. The `ObserverPipeline` calls `start_all()` during initialization and `stop_all()` during shutdown.

### observe()

Called after each turn. Returns a list of `Observation` objects representing the current state. Even continuous observers should implement `observe()` to report their latest findings on demand.

---

## Observation Model

```python
class Observation(BaseModel):
    id: str                           # Unique ID
    observer_name: str                # Which observer produced this
    thread_id: str                    # Associated thread
    turn_id: str | None               # Associated turn (if applicable)
    severity: ObservationSeverity     # info, warning, error, critical
    title: str                        # Short summary
    details: str                      # Longer description
    data: dict                        # Structured payload
    timestamp: datetime               # When observed
    source_file: str | None           # Source file (if applicable)
    source_line: int | None           # Source line (if applicable)
```

### Severity Levels

| Level | Meaning | Agent Impact |
|-------|---------|-------------|
| `info` | Normal status update | Not included in agent context (filtered out) |
| `warning` | Potential issue | Included in observation summary |
| `error` | Definite problem | Included and highlighted in observation summary |
| `critical` | Severe issue | Included and highlighted; may trigger escalation |

---

## Observer Pipeline

The `ObserverPipeline` orchestrates all observers:

```python
from devharness.observers.pipeline import ObserverPipeline

pipeline = ObserverPipeline(event_bus=event_bus)
pipeline.add_observer(ProcessObserver())
pipeline.add_observer(TestObserver())
pipeline.add_observer(LintObserver())
```

### observe_all()

Called by the runtime after each turn:

1. Run all observers concurrently.
2. Collect all observations.
3. Emit each observation as an event on the bus.
4. Return the combined list.

### Pipeline Methods

| Method | Description |
|--------|-------------|
| `add_observer(observer)` | Register an observer |
| `remove_observer(name)` | Remove by name |
| `observe_all(thread, turn)` | Run all observers, return observations |
| `start_all()` | Start continuous monitoring on all observers |
| `stop_all()` | Stop all continuous monitoring |
| `list_observers()` | Return names of registered observers |

---

## Observation Summary

After observations are collected, they are aggregated into an `ObservationSummary`:

```python
from devharness.observers.summary import build_observation_summary, format_summary_for_agent

summary = build_observation_summary(
    thread_id=thread.id,
    turn_id=turn.id,
    observations=observations,
)

text = format_summary_for_agent(summary)
```

### ObservationSummary Model

```python
class ObservationSummary(BaseModel):
    thread_id: str
    turn_id: str
    observations: list[Observation]
    process_status: dict[str, str]     # process name -> status
    test_summary: TestSummary | None   # aggregate test results
    endpoint_summary: EndpointSummary | None
    new_errors: int
    new_warnings: int
    generated_at: datetime
```

### Agent Context Format

The formatted summary looks like:

```
[OBSERVATION REPORT - since your last action]
- Process: dev-server - crashed
- Tests: 42 passed, 3 failed, 0 errored
  - test_login: Expected 200, got 401
    at tests/test_auth.py:42
- logs: New RuntimeError in app.log
  TypeError: cannot unpack non-sequence NoneType
```

Or if everything is clean:

```
[OBSERVATION REPORT - since your last action]
- No issues detected.
```

The summary limits output (e.g., max 5 test failures, max 10 error observations) to prevent context bloat.

---

## Built-in Observers

### ProcessObserver

Monitors background process health using `psutil`. Detects:

- Process crashes (expected process not running)
- High CPU/memory usage
- Zombie processes

Requires: `pip install devharness[observers]`

### TestObserver

Parses test runner output and produces a `TestSummary`:

```python
class TestSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errored: int
    skipped: int
    failures: list[TestFailure]
    coverage_pct: float | None
    coverage_diff: float | None
```

Each `TestFailure` includes the test name, file path, line number, assertion message, and stack trace.

### LintObserver

Monitors linter output (ruff, eslint, etc.) for new warnings and errors.

### BuildObserver

Monitors build process output (compilation, bundling). Reports build failures with error output.

### LogObserver

Tails log files and reports new error-level entries. Configurable log paths and error patterns.

### EndpointObserver

Performs HTTP health checks against configured endpoints:

```python
class EndpointStatus(BaseModel):
    url: str
    status_code: int | None
    response_time_ms: float | None
    is_healthy: bool
    error: str | None
```

Reports unhealthy endpoints with status codes and error messages.

### BrowserObserver

Integrates with the browser testing system. Runs browser test flows and reports results including:

- Console errors
- Visual regressions
- Interaction failures
- DOM state

See [Browser Testing](browser-testing.md) for full details.

### MetricsObserver

Monitors application metrics (response times, error rates, throughput). Configurable metric sources and thresholds.

---

## Writing a Custom Observer

### Step 1: Implement BaseObserver

```python
from devharness.observers.base import BaseObserver
from devharness.core.models import (
    Observation,
    ObservationSeverity,
    Thread,
    Turn,
)

class DatabaseObserver(BaseObserver):
    name = "database"

    def __init__(self, connection_string: str):
        self._conn_string = connection_string
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        observations = []

        # Check connection pool
        pool_info = await check_pool_health(self._conn_string)
        if pool_info["available"] < 2:
            observations.append(Observation(
                observer_name=self.name,
                thread_id=thread.id,
                turn_id=turn.id if turn else None,
                severity=ObservationSeverity.WARNING,
                title="Connection pool nearly exhausted",
                details=f"Available connections: {pool_info['available']}/{pool_info['total']}",
                data=pool_info,
            ))

        # Check for slow queries
        slow_queries = await get_slow_queries(self._conn_string, threshold_ms=1000)
        for query in slow_queries:
            observations.append(Observation(
                observer_name=self.name,
                thread_id=thread.id,
                turn_id=turn.id if turn else None,
                severity=ObservationSeverity.WARNING,
                title=f"Slow query: {query['duration_ms']}ms",
                details=query["sql"][:500],
                data={"duration_ms": query["duration_ms"]},
            ))

        return observations

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
```

### Step 2: Register

```python
pipeline.add_observer(DatabaseObserver("postgresql://localhost/mydb"))
```

### Step 3: Verify

After your observer is registered, it runs automatically after every turn. Check the observation summary in the agent's context to confirm your observations are surfacing.

---

## Event Integration

Every observation is emitted as an event on the bus:

```python
Event(
    thread_id=thread.id,
    turn_id=turn.id,
    kind=EventKind.OBSERVATION,
    data=observation.model_dump(mode="json"),
)
```

This means observations are:

- Persisted to SQLite (via the storage subscriber)
- Available to the web UI (via SSE)
- Available to Slack (via the Slack subscriber)
- Queryable via the events API
