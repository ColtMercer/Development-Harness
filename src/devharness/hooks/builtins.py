"""Built-in hook implementations.

Each function returns a ``HookConfig`` that can be registered with a
``HookRegistry``.  These hooks follow the exit-code contract:

- Exit 0 on success (output swallowed -- silent).
- Exit 2 to re-engage the agent with stdout as context (e.g. failure
  details the agent should act on).
- Other codes log a warning and continue.
"""

from __future__ import annotations

from devharness.core.models import HookConfig, HookEvent


def format_check_hook(
    *,
    event: HookEvent = HookEvent.PRE_COMMIT,
    timeout: int = 60,
) -> HookConfig:
    """Hook that runs ``ruff format --check``.

    Exits 0 if formatting is clean; exits 2 with diff output if there are
    formatting issues so the agent can fix them.
    """
    script = (
        "ruff format --check . 2>&1 && exit 0 || "
        "{ echo 'Formatting issues detected:'; ruff format --diff . 2>&1; exit 2; }"
    )
    return HookConfig(
        name="format_check",
        event=event,
        script=script,
        timeout=timeout,
    )


def typecheck_hook(
    *,
    event: HookEvent = HookEvent.PRE_COMMIT,
    timeout: int = 120,
) -> HookConfig:
    """Hook that runs ``mypy``.

    Exits 0 if types are clean; exits 2 with mypy output on type errors
    so the agent can address them.
    """
    script = "mypy . 2>&1 && exit 0 || { mypy . 2>&1; exit 2; }"
    return HookConfig(
        name="typecheck",
        event=event,
        script=script,
        timeout=timeout,
    )


def test_hook(
    *,
    event: HookEvent = HookEvent.POST_TOOL_CALL,
    on_tools: list[str] | None = None,
    timeout: int = 300,
) -> HookConfig:
    """Hook that runs ``pytest``.

    Success is swallowed (exit 0); failures are surfaced to the agent
    (exit 2) with the pytest output so it can diagnose and fix.
    """
    script = (
        "pytest --tb=short -q 2>&1 && exit 0 || "
        "{ pytest --tb=short -q 2>&1; exit 2; }"
    )
    return HookConfig(
        name="test",
        event=event,
        script=script,
        on_tools=on_tools,
        timeout=timeout,
    )
