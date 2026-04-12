"""Task DAG management.

Provides helpers to build, query, and update a TaskDAG -- the dependency
graph that drives parallel task execution.
"""

from __future__ import annotations

from devharness.core.models import TaskDAG, TaskNode, TaskStatus, _new_id


class TaskDAGManager:
    """Stateless helper for creating and mutating TaskDAG instances."""

    def create_dag(self, goal: str, tasks: list[dict]) -> TaskDAG:
        """Build a TaskDAG from a goal string and a list of task dicts.

        Each dict in *tasks* must contain at least ``content`` (str).
        Optional keys:
        - ``id``         – explicit node id (auto-generated if absent)
        - ``blocked_by`` – list of node ids this task depends on
        """
        nodes: list[TaskNode] = []
        for t in tasks:
            node = TaskNode(
                id=t.get("id", _new_id()),
                content=t["content"],
                blocked_by=t.get("blocked_by", []),
            )
            nodes.append(node)
        return TaskDAG(goal=goal, nodes=nodes)

    def mark_completed(self, dag: TaskDAG, node_id: str, result: str) -> None:
        """Mark *node_id* as completed with the given *result*."""
        node = self._find_node(dag, node_id)
        node.status = TaskStatus.COMPLETED
        node.result = result

    def mark_failed(self, dag: TaskDAG, node_id: str, error: str) -> None:
        """Mark *node_id* as failed and record the *error*."""
        node = self._find_node(dag, node_id)
        node.status = TaskStatus.FAILED
        node.error = error

    def get_ready_nodes(self, dag: TaskDAG) -> list[TaskNode]:
        """Return nodes whose dependencies are all satisfied (completed)."""
        return dag.ready_nodes()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_node(dag: TaskDAG, node_id: str) -> TaskNode:
        for node in dag.nodes:
            if node.id == node_id:
                return node
        raise KeyError(f"Node {node_id!r} not found in DAG {dag.id!r}")
