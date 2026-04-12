"""Task executor -- runs a TaskDAG to completion.

Independent (ready) nodes execute in parallel via anyio task groups.
The executor loops until every node is completed or failed.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Protocol

import anyio

from devharness.core.errors import AgentError
from devharness.core.models import TaskDAG, TaskNode, TaskStatus
from devharness.tasks.dag import TaskDAGManager

logger = logging.getLogger(__name__)


class AgentBackend(Protocol):
    """Minimal interface expected from an agent backend."""

    async def run(self, prompt: str, **kwargs: Any) -> str: ...


class TaskExecutor:
    """Execute a TaskDAG by dispatching ready nodes to sub-agents."""

    def __init__(self, dag_manager: TaskDAGManager | None = None) -> None:
        self._dag = dag_manager or TaskDAGManager()

    async def execute_dag(
        self,
        dag: TaskDAG,
        agent_backend: AgentBackend,
        *,
        max_iterations: int = 200,
    ) -> TaskDAG:
        """Run the select-and-dispatch loop until the DAG is complete.

        At each iteration the executor finds ready nodes, spawns them in
        parallel, then marks them completed or failed based on the
        agent's response.

        Parameters
        ----------
        dag:
            The task graph to execute.
        agent_backend:
            An object implementing the ``AgentBackend`` protocol (must
            expose an async ``run`` method).
        max_iterations:
            Safety cap to prevent infinite loops.

        Returns
        -------
        TaskDAG
            The same *dag* instance, mutated in place.
        """
        iteration = 0
        while not dag.is_complete and iteration < max_iterations:
            iteration += 1
            ready = self._dag.get_ready_nodes(dag)

            if not ready:
                # Nothing ready but DAG isn't complete -- remaining nodes
                # are blocked by failed dependencies. Mark them BLOCKED.
                self._mark_blocked(dag)
                break

            async with anyio.create_task_group() as tg:
                for node in ready:
                    node.status = TaskStatus.RUNNING
                    tg.start_soon(self._run_node, dag, node, agent_backend)

        return dag

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run_node(
        self,
        dag: TaskDAG,
        node: TaskNode,
        agent_backend: AgentBackend,
    ) -> None:
        """Execute a single node via the agent backend."""
        start = time.monotonic()
        try:
            result = await agent_backend.run(node.content)
            elapsed = time.monotonic() - start
            logger.info(
                "Node %s completed in %.1fs",
                node.id,
                elapsed,
            )
            self._dag.mark_completed(dag, node.id, result)
        except Exception as exc:
            elapsed = time.monotonic() - start
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "Node %s failed after %.1fs: %s",
                node.id,
                elapsed,
                error_msg,
            )
            self._dag.mark_failed(dag, node.id, error_msg)

    def _mark_blocked(self, dag: TaskDAG) -> None:
        """Mark all remaining PENDING nodes as BLOCKED."""
        failed_ids = {n.id for n in dag.nodes if n.status == TaskStatus.FAILED}
        for node in dag.nodes:
            if node.status == TaskStatus.PENDING:
                if any(dep in failed_ids for dep in node.blocked_by):
                    node.status = TaskStatus.BLOCKED
                    node.error = "Blocked by failed dependency"
