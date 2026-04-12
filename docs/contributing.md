# Contributing Guide

Thank you for contributing to the Development Harness. This guide covers development setup, code style, testing, pull request process, and architecture guidelines.

---

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git
- Claude Code CLI (for integration testing with the Claude Code backend)
- Docker (optional, for Neo4j integration testing)

### Clone and Install

```bash
git clone https://github.com/ColtMercer/Development-Harness.git
cd Development-Harness
pip install -e ".[dev,all]"
```

This installs the package in editable mode with all development and optional dependencies.

### Verify Setup

```bash
pytest
ruff check .
mypy src/devharness/
```

---

## Code Style

### Formatting and Linting

The project uses [Ruff](https://docs.astral.sh/ruff/) for formatting and linting.

```bash
# Check formatting
ruff format --check .

# Auto-format
ruff format .

# Lint
ruff check .

# Lint with auto-fix
ruff check --fix .
```

Configuration is in `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
```

### Type Checking

The project uses [mypy](https://mypy-lang.org/) for type checking.

```bash
mypy src/devharness/
```

Configuration is in `pyproject.toml`:

```toml
[tool.mypy]
python_version = "3.11"
strict = false
warn_return_any = true
warn_unused_configs = true
```

We do not yet enforce `strict = true`, but new code should use type annotations throughout.

### Style Guidelines

- **All domain models** live in `core/models.py`. Do not create model files in subpackages.
- **Imports**: Use `from __future__ import annotations` in every module.
- **Async**: Use `anyio` for async operations, not `asyncio` directly. This allows backend flexibility.
- **Error handling**: Raise from the `HarnessError` hierarchy (`core/errors.py`). Create new error classes there if needed.
- **Logging**: Use `logging.getLogger(__name__)` per module.
- **Docstrings**: Google-style docstrings for public classes and functions. Include `Parameters`, `Returns`, and `Raises` sections where appropriate.
- **Constants**: Module-level constants prefixed with underscore (`_TERM_GRACE_SECONDS`).

---

## Testing

### Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=devharness --cov-report=term-missing

# Specific test file
pytest tests/test_event_bus.py

# Specific test
pytest tests/test_event_bus.py::test_emit_calls_handlers -v
```

### Test Configuration

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

The `asyncio_mode = "auto"` setting means async test functions are automatically detected and run with the async test runner.

### Writing Tests

- Place tests in the `tests/` directory mirroring the source structure.
- Name test files `test_<module>.py`.
- Name test functions `test_<behavior>`.
- Use `pytest-asyncio` for async tests (auto-detected with `asyncio_mode = "auto"`).
- Mock external dependencies (subprocesses, file I/O, network) in unit tests.
- Integration tests that spawn real subprocesses should be marked with `@pytest.mark.integration` (or similar) so they can be skipped in CI environments without CLIs installed.

Example:

```python
import pytest
from devharness.core.event_bus import EventBus
from devharness.core.models import Event, EventKind

async def test_emit_calls_matching_handlers():
    bus = EventBus()
    received = []

    async def handler(event: Event):
        received.append(event)

    bus.subscribe(EventKind.TURN_START, handler)

    event = Event(
        thread_id="test-thread",
        kind=EventKind.TURN_START,
    )
    await bus.emit(event)

    assert len(received) == 1
    assert received[0].kind == EventKind.TURN_START
```

---

## Pull Request Process

### Before Submitting

1. **Create a branch** from `main`:

   ```bash
   git checkout -b feature/my-feature
   ```

2. **Make your changes** following the code style guidelines.

3. **Run the full check suite:**

   ```bash
   ruff format --check .
   ruff check .
   mypy src/devharness/
   pytest
   ```

4. **Write tests** for new functionality.

5. **Commit** with a clear, descriptive message.

### PR Guidelines

- **Keep PRs focused.** One feature or fix per PR. If you find something else to fix while working, submit it as a separate PR.
- **Title**: Short, imperative (`Add custom observer support`, `Fix hook timeout handling`).
- **Description**: Explain what the PR does and why. Include any design decisions.
- **Tests**: New features need tests. Bug fixes should include a regression test.
- **Documentation**: Update relevant docs if behavior changes.

### Review Process

- At least one maintainer review is required.
- CI must pass (formatting, linting, type checking, tests).
- Merge via squash merge to keep history clean.

---

## Architecture Guidelines

When contributing new features, follow these architectural principles:

### 1. Models Go in models.py

All Pydantic domain models belong in `core/models.py`. This is a deliberate choice to prevent circular imports. Do not create model files in subpackages.

### 2. Use the Event Bus

New features that produce observable state changes should emit events via the event bus. Define new `EventKind` values in `core/models.py` if the existing ones do not cover your case.

### 3. Implement Interfaces

New backends, observers, verifiers, tools, skills, and policy rules should implement the corresponding abstract base class. This ensures they are pluggable and testable.

| What | Interface | Location |
|------|-----------|----------|
| Agent backend | `AgentBackend` | `agents/base.py` |
| Tool | `BaseTool` | `tools/base.py` |
| Observer | `BaseObserver` | `observers/base.py` |
| Verifier | `BaseVerifier` | `verification/base.py` |
| Skill | `BaseSkill` | `skills/base.py` |
| Policy rule | `PolicyRule` | `policies/rules.py` |
| Memory backend | `MemoryBackend` | `memory/service.py` |
| Storage backend | `StorageBackend` | `storage/base.py` |

### 4. Async-First

All I/O operations should be async. Use `anyio` for subprocess management, task groups, and semaphores. Do not use `asyncio` directly -- `anyio` provides backend flexibility.

### 5. Fail Gracefully

Optional systems (memory, Slack, observers) must not crash the harness. Wrap calls in try/except, log warnings, and continue. The `MemoryService` facade is the reference example for graceful degradation.

### 6. No Config Files

Configuration goes in the SQLite database or environment variables. Do not add YAML, TOML, or JSON config files that users need to edit manually.

### 7. Concurrent Pipelines

Observers and verifiers run concurrently via `anyio.create_task_group()`. Individual failures are caught and logged, not propagated. Follow this pattern for any new concurrent pipeline.

---

## Adding Dependencies

- Core dependencies (those needed for basic operation) go in `[project.dependencies]`.
- Optional dependencies go in `[project.optional-dependencies]` under an appropriate group.
- Development dependencies go in the `dev` group.
- Keep dependency version ranges as wide as possible while being compatible.

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
