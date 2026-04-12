"""Example: Write documentation for a module.

Uses the docs/writer skill.

Usage:
    python examples/write_docs.py
    # or
    harness run --skill docs/writer "Write docs for the auth module"
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
        approval_mode="workspace_write",
        skills=["docs/writer"],
        verification_enabled=True,
        workspace_root=".",
    )
    thread = await runtime.create_thread(thread_config)
    print(f"Created thread: {thread.id}")

    turn = await runtime.run_turn(
        thread.id,
        "Write comprehensive documentation for the tools module. Include:\n"
        "1. Module overview and purpose\n"
        "2. How to create a custom tool\n"
        "3. Tool registration and schema generation\n"
        "4. Built-in tools reference\n"
        "5. Code examples\n"
        "Write as Markdown in docs/tools.md.",
    )

    if turn.assistant_response:
        print(f"\nAgent response:\n{turn.assistant_response[:500]}")

    await shutdown(runtime)


if __name__ == "__main__":
    anyio.run(main)
