"""Example: Investigate a failing service.

Uses the sre/investigator skill with endpoint and log observers.

Usage:
    python examples/investigate_service.py
    # or
    harness run --skill sre/investigator "Investigate why the API is returning 500 errors"
"""

import anyio

from devharness.bootstrap import bootstrap, shutdown
from devharness.core.config import load_config
from devharness.core.models import ThreadConfig


async def main() -> None:
    config = load_config()
    runtime = await bootstrap(config)

    thread_config = ThreadConfig(
        agent_backend="claude-code",
        approval_mode="auto_approve_safe",
        skills=["sre/investigator"],
        verification_enabled=True,
        workspace_root=".",
    )
    thread = await runtime.create_thread(thread_config)
    print(f"Created thread: {thread.id}")

    turn = await runtime.run_turn(
        thread.id,
        "The API service is returning 500 errors on the /api/users endpoint. "
        "Investigate the issue:\n"
        "1. Check recent git changes\n"
        "2. Review error logs\n"
        "3. Run the test suite to identify failing tests\n"
        "4. Identify the root cause\n"
        "5. Propose and implement a fix\n"
        "6. Verify the fix resolves the issue",
    )

    if turn.assistant_response:
        print(f"\nInvestigation Report:\n{turn.assistant_response}")

    if turn.verification:
        print(f"\nVerification: {'PASSED' if turn.verification.all_passed else 'FAILED'}")

    await shutdown(runtime)


if __name__ == "__main__":
    anyio.run(main)
