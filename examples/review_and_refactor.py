"""Example: Review a repo and propose refactoring.

Uses the coding/reviewer skill with read-only approval mode.

Usage:
    python examples/review_and_refactor.py
    # or
    harness run --skill coding/reviewer --approval-mode read_only "Review this codebase"
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
        approval_mode="read_only",  # reviewer shouldn't modify files
        skills=["coding/reviewer"],
        verification_enabled=False,
        workspace_root=".",
    )
    thread = await runtime.create_thread(thread_config)
    print(f"Created thread: {thread.id}")

    turn = await runtime.run_turn(
        thread.id,
        "Review this codebase for code quality issues, architectural problems, "
        "and potential improvements. Focus on:\n"
        "1. Code organization and module boundaries\n"
        "2. Error handling patterns\n"
        "3. Test coverage gaps\n"
        "4. Performance concerns\n"
        "5. Security considerations\n"
        "Produce a structured report with prioritized recommendations.",
    )

    if turn.assistant_response:
        print(f"\nReview Report:\n{turn.assistant_response}")

    await shutdown(runtime)


if __name__ == "__main__":
    anyio.run(main)
