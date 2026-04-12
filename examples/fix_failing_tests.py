"""Example: Fix failing tests using the harness.

This example demonstrates the core harness loop:
1. Create a thread with the test_fixer skill
2. Run a turn asking the agent to fix failing tests
3. The harness delegates to Claude Code, runs observers, verifies the fix

Usage:
    python examples/fix_failing_tests.py
    # or
    harness run --skill test/fixer "Fix the failing tests in the test suite"
"""

import anyio

from devharness.bootstrap import bootstrap, shutdown
from devharness.core.config import load_config
from devharness.core.models import ThreadConfig


async def main() -> None:
    config = load_config()
    runtime = await bootstrap(config)

    # Create a thread with test_fixer skill and verification enabled
    thread_config = ThreadConfig(
        agent_backend="claude-code",
        approval_mode="auto_approve_safe",
        skills=["test/fixer"],
        verification_enabled=True,
        workspace_root=".",
    )
    thread = await runtime.create_thread(thread_config)
    print(f"Created thread: {thread.id}")

    # Run the turn
    turn = await runtime.run_turn(
        thread.id,
        "Run the test suite, identify failing tests, and fix them. "
        "After fixing, verify all tests pass.",
    )

    # Print results
    if turn.assistant_response:
        print(f"\nAgent response:\n{turn.assistant_response}")

    if turn.verification:
        status = "PASSED" if turn.verification.all_passed else "FAILED"
        print(f"\nVerification: {status}")
        for r in turn.verification.results:
            print(f"  {'PASS' if r.passed else 'FAIL'} {r.verifier_name}: {r.message}")

    if turn.error:
        print(f"\nError: {turn.error}")

    print(f"\nThread: {thread.id} | Status: completed")
    print(f"Tool calls: {len(turn.tool_calls)}")

    await shutdown(runtime)


if __name__ == "__main__":
    anyio.run(main)
