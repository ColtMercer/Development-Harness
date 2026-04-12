"""Protocol method registry -- maps JSON-RPC methods to runtime handlers."""

from __future__ import annotations

from typing import Any

from devharness.app_server.jsonrpc import JsonRpcDispatcher
from devharness.core.runtime import Runtime


def register_methods(dispatcher: JsonRpcDispatcher, runtime: Runtime) -> None:
    """Register all JSON-RPC methods with the dispatcher."""

    async def thread_create(**params: Any) -> dict:
        from devharness.core.models import ThreadConfig

        config = ThreadConfig(**params) if params else None
        thread = await runtime.create_thread(config)
        return thread.model_dump(mode="json")

    async def thread_run(**params: Any) -> dict:
        thread_id = params["thread_id"]
        user_input = params["user_input"]
        turn = await runtime.run_turn(thread_id, user_input)
        return turn.model_dump(mode="json")

    async def thread_get(**params: Any) -> dict:
        thread = await runtime.get_thread(params["thread_id"])
        return thread.model_dump(mode="json")

    async def thread_list(**params: Any) -> list[dict]:
        threads = await runtime.list_threads(params.get("project_id"))
        return [t.model_dump(mode="json") for t in threads]

    async def thread_cancel(**params: Any) -> None:
        await runtime.cancel_thread(params["thread_id"])

    async def approval_resolve(**params: Any) -> None:
        await runtime.resolve_approval(
            params["thread_id"],
            params["approval_id"],
            params["approved"],
            params.get("reason", ""),
        )

    async def events_stream(**params: Any) -> list[dict]:
        events = []
        async for event in runtime.replay_thread(params["thread_id"]):
            events.append(event.model_dump(mode="json"))
        return events

    async def artifacts_list(**params: Any) -> list[dict]:
        arts = await runtime._artifacts.list_for_thread(params["thread_id"])
        return [a.model_dump(mode="json") for a in arts]

    async def skills_list(**params: Any) -> list[dict]:
        skills = runtime._skills.list_skills()
        return [s.model_dump(mode="json") for s in skills]

    async def agents_list(**params: Any) -> list[str]:
        return list(runtime._agents.keys())

    # Register all methods
    dispatcher.register("thread/create", thread_create)
    dispatcher.register("thread/run", thread_run)
    dispatcher.register("thread/get", thread_get)
    dispatcher.register("thread/list", thread_list)
    dispatcher.register("thread/cancel", thread_cancel)
    dispatcher.register("approval/resolve", approval_resolve)
    dispatcher.register("events/stream", events_stream)
    dispatcher.register("artifacts/list", artifacts_list)
    dispatcher.register("skills/list", skills_list)
    dispatcher.register("agents/list", agents_list)
