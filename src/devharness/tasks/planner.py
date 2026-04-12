"""Read-only planner -- decomposes a prompt into a TaskDAG.

Uses a sub-agent to break a high-level task description into smaller,
dependency-aware sub-tasks represented as a TaskDAG.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from devharness.core.models import TaskDAG
from devharness.tasks.dag import TaskDAGManager

logger = logging.getLogger(__name__)

_DECOMPOSE_SYSTEM_PROMPT = """\
You are a task decomposition assistant. Given a goal, break it into
small, actionable sub-tasks. Return a JSON object with this shape:

{
  "tasks": [
    {"id": "t1", "content": "description of task 1", "blocked_by": []},
    {"id": "t2", "content": "description of task 2", "blocked_by": ["t1"]}
  ]
}

Rules:
- Each task must have a unique ``id``, a ``content`` description, and a
  ``blocked_by`` list of task ids it depends on.
- Keep tasks small and self-contained.
- Return ONLY valid JSON -- no markdown fences, no commentary.
"""


class PlannerBackend(Protocol):
    """Minimal interface for the agent used by the planner."""

    async def run(self, prompt: str, **kwargs: Any) -> str: ...


async def decompose_task(
    prompt: str,
    agent_backend: PlannerBackend,
    *,
    dag_manager: TaskDAGManager | None = None,
) -> TaskDAG:
    """Decompose *prompt* into a TaskDAG using a sub-agent.

    The agent is called with a system prompt that instructs it to return
    a JSON array of tasks with dependencies. The response is parsed and
    converted into a :class:`TaskDAG`.
    """
    manager = dag_manager or TaskDAGManager()

    combined_prompt = (
        f"{_DECOMPOSE_SYSTEM_PROMPT}\n\n"
        f"Goal to decompose:\n{prompt}"
    )

    raw = await agent_backend.run(combined_prompt)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Planner returned non-JSON; wrapping as single task")
        data = {"tasks": [{"id": "t1", "content": prompt, "blocked_by": []}]}

    tasks = data.get("tasks", data) if isinstance(data, dict) else data
    if not isinstance(tasks, list):
        tasks = [{"id": "t1", "content": prompt, "blocked_by": []}]

    return manager.create_dag(goal=prompt, tasks=tasks)
