"""Example: Fix a frontend bug using browser testing.

Demonstrates browser testing integration:
1. Agent makes UI changes
2. Browser observer runs Playwright flows
3. Agent sees screenshots and console errors
4. Agent self-corrects until browser tests pass

Usage:
    python examples/fix_frontend_bug.py
"""

import anyio

from devharness.bootstrap import bootstrap, shutdown
from devharness.core.config import load_config
from devharness.core.models import ThreadConfig


async def main() -> None:
    config = load_config()
    runtime = await bootstrap(config)

    # Create thread with browser testing enabled
    thread_config = ThreadConfig(
        agent_backend="claude-code",
        approval_mode="auto_approve_safe",
        skills=["coding/general"],
        verification_enabled=True,
        workspace_root=".",
    )
    thread = await runtime.create_thread(thread_config)
    print(f"Created thread: {thread.id}")

    # Run the turn with browser test context
    turn = await runtime.run_turn(
        thread.id,
        "The login button on the login page is not working. "
        "Users click 'Login' and nothing happens. "
        "Fix the bug and verify the login flow works by testing it. "
        "The login page is at http://localhost:3000/login.",
    )

    if turn.assistant_response:
        print(f"\nAgent response:\n{turn.assistant_response[:500]}")

    if turn.error:
        print(f"\nError: {turn.error}")

    # Check browser test results in observations
    observations = await runtime._storage.load_observations(thread.id)
    browser_obs = [o for o in observations if o.observer_name == "browser"]
    for obs in browser_obs:
        print(f"\nBrowser: [{obs.severity}] {obs.title}")
        if obs.details:
            print(f"  {obs.details[:200]}")

    await shutdown(runtime)


if __name__ == "__main__":
    anyio.run(main)
