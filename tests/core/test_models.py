"""Tests for devharness.core.models."""

from __future__ import annotations

from datetime import datetime, timezone

from devharness.core.models import (
    ApprovalMode,
    ContextBudget,
    Event,
    EventKind,
    Plan,
    Step,
    StepStatus,
    TaskDAG,
    TaskNode,
    TaskStatus,
    Thread,
    ThreadConfig,
    ThreadStatus,
    Turn,
)


# ---------------------------------------------------------------------------
# Thread / Turn / Event creation with defaults
# ---------------------------------------------------------------------------


class TestThreadDefaults:
    def test_thread_has_id(self) -> None:
        t = Thread()
        assert len(t.id) == 12

    def test_thread_default_status(self) -> None:
        t = Thread()
        assert t.status == ThreadStatus.PENDING

    def test_thread_default_config(self) -> None:
        t = Thread()
        assert isinstance(t.config, ThreadConfig)

    def test_thread_created_at_is_utc(self) -> None:
        t = Thread()
        assert t.created_at.tzinfo is not None

    def test_thread_turns_empty(self) -> None:
        t = Thread()
        assert t.turns == []

    def test_thread_metadata_empty(self) -> None:
        t = Thread()
        assert t.metadata == {}


class TestTurnDefaults:
    def test_turn_has_id(self) -> None:
        turn = Turn(thread_id="abc", user_input="do something")
        assert len(turn.id) == 12

    def test_turn_stores_user_input(self) -> None:
        turn = Turn(thread_id="abc", user_input="hello")
        assert turn.user_input == "hello"

    def test_turn_no_assistant_response(self) -> None:
        turn = Turn(thread_id="abc", user_input="x")
        assert turn.assistant_response is None

    def test_turn_tool_calls_empty(self) -> None:
        turn = Turn(thread_id="abc", user_input="x")
        assert turn.tool_calls == []


class TestEventDefaults:
    def test_event_has_id(self) -> None:
        e = Event(thread_id="t1", kind=EventKind.THREAD_CREATED)
        assert len(e.id) == 12

    def test_event_timestamp_set(self) -> None:
        e = Event(thread_id="t1", kind=EventKind.TURN_START)
        assert isinstance(e.timestamp, datetime)

    def test_event_data_default_empty(self) -> None:
        e = Event(thread_id="t1", kind=EventKind.OBSERVATION)
        assert e.data == {}

    def test_event_turn_id_optional(self) -> None:
        e = Event(thread_id="t1", kind=EventKind.THREAD_CREATED)
        assert e.turn_id is None


# ---------------------------------------------------------------------------
# ThreadConfig validation
# ---------------------------------------------------------------------------


class TestThreadConfig:
    def test_default_approval_mode(self) -> None:
        cfg = ThreadConfig()
        assert cfg.approval_mode == ApprovalMode.AUTO_APPROVE_SAFE

    def test_default_max_turns(self) -> None:
        cfg = ThreadConfig()
        assert cfg.max_turns == 50

    def test_allowed_tools_none_means_all(self) -> None:
        cfg = ThreadConfig()
        assert cfg.allowed_tools is None

    def test_denied_tools_none_by_default(self) -> None:
        cfg = ThreadConfig()
        assert cfg.denied_tools is None

    def test_custom_config(self) -> None:
        cfg = ThreadConfig(
            approval_mode=ApprovalMode.READ_ONLY,
            max_turns=10,
            allowed_tools=["file_read"],
            denied_tools=["shell"],
        )
        assert cfg.approval_mode == ApprovalMode.READ_ONLY
        assert cfg.max_turns == 10
        assert cfg.allowed_tools == ["file_read"]
        assert cfg.denied_tools == ["shell"]

    def test_context_window_default(self) -> None:
        cfg = ThreadConfig()
        assert cfg.context_window == 200_000


# ---------------------------------------------------------------------------
# Plan with Steps
# ---------------------------------------------------------------------------


class TestPlan:
    def test_plan_has_id(self) -> None:
        plan = Plan(goal="build a feature")
        assert len(plan.id) == 12

    def test_plan_goal(self) -> None:
        plan = Plan(goal="deploy the app")
        assert plan.goal == "deploy the app"

    def test_plan_empty_steps(self) -> None:
        plan = Plan(goal="test")
        assert plan.steps == []

    def test_plan_with_steps(self) -> None:
        steps = [
            Step(sequence=0, description="Write code"),
            Step(sequence=1, description="Run tests"),
        ]
        plan = Plan(goal="implement feature", steps=steps)
        assert len(plan.steps) == 2
        assert plan.steps[0].description == "Write code"
        assert plan.steps[1].status == StepStatus.PENDING

    def test_plan_current_step_index(self) -> None:
        plan = Plan(goal="test")
        assert plan.current_step_index == 0


# ---------------------------------------------------------------------------
# TaskDAG.ready_nodes() and is_complete
# ---------------------------------------------------------------------------


class TestTaskDAG:
    def test_ready_nodes_no_deps(self) -> None:
        node_a = TaskNode(id="a", content="task a")
        node_b = TaskNode(id="b", content="task b")
        dag = TaskDAG(goal="test", nodes=[node_a, node_b])
        ready = dag.ready_nodes()
        assert len(ready) == 2

    def test_ready_nodes_with_deps(self) -> None:
        node_a = TaskNode(id="a", content="task a")
        node_b = TaskNode(id="b", content="task b", blocked_by=["a"])
        dag = TaskDAG(goal="test", nodes=[node_a, node_b])
        ready = dag.ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "a"

    def test_ready_nodes_after_completion(self) -> None:
        node_a = TaskNode(id="a", content="task a", status=TaskStatus.COMPLETED)
        node_b = TaskNode(id="b", content="task b", blocked_by=["a"])
        dag = TaskDAG(goal="test", nodes=[node_a, node_b])
        ready = dag.ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_ready_nodes_multiple_deps(self) -> None:
        node_a = TaskNode(id="a", content="task a", status=TaskStatus.COMPLETED)
        node_b = TaskNode(id="b", content="task b", status=TaskStatus.PENDING)
        node_c = TaskNode(
            id="c", content="task c", blocked_by=["a", "b"]
        )
        dag = TaskDAG(goal="test", nodes=[node_a, node_b, node_c])
        # c is blocked because b is not completed
        ready = dag.ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_is_complete_all_completed(self) -> None:
        nodes = [
            TaskNode(id="a", content="a", status=TaskStatus.COMPLETED),
            TaskNode(id="b", content="b", status=TaskStatus.COMPLETED),
        ]
        dag = TaskDAG(goal="test", nodes=nodes)
        assert dag.is_complete is True

    def test_is_complete_mixed_completed_failed(self) -> None:
        nodes = [
            TaskNode(id="a", content="a", status=TaskStatus.COMPLETED),
            TaskNode(id="b", content="b", status=TaskStatus.FAILED),
        ]
        dag = TaskDAG(goal="test", nodes=nodes)
        assert dag.is_complete is True

    def test_is_complete_with_pending(self) -> None:
        nodes = [
            TaskNode(id="a", content="a", status=TaskStatus.COMPLETED),
            TaskNode(id="b", content="b", status=TaskStatus.PENDING),
        ]
        dag = TaskDAG(goal="test", nodes=nodes)
        assert dag.is_complete is False

    def test_is_complete_empty(self) -> None:
        dag = TaskDAG(goal="test", nodes=[])
        assert dag.is_complete is True


# ---------------------------------------------------------------------------
# ContextBudget properties
# ---------------------------------------------------------------------------


class TestContextBudget:
    def test_used_tokens(self) -> None:
        budget = ContextBudget(
            max_tokens=200_000,
            tier1_tokens=10_000,
            tier2_tokens=20_000,
            tier3_tokens=5_000,
        )
        assert budget.used_tokens == 35_000

    def test_remaining(self) -> None:
        budget = ContextBudget(
            max_tokens=200_000,
            tier1_tokens=10_000,
            tier2_tokens=20_000,
            tier3_tokens=5_000,
        )
        assert budget.remaining == 165_000

    def test_utilization(self) -> None:
        budget = ContextBudget(
            max_tokens=100_000,
            tier1_tokens=20_000,
            tier2_tokens=20_000,
            tier3_tokens=0,
        )
        assert budget.utilization == 0.4

    def test_utilization_zero_max(self) -> None:
        budget = ContextBudget(max_tokens=0)
        assert budget.utilization == 0.0

    def test_default_budget(self) -> None:
        budget = ContextBudget()
        assert budget.max_tokens == 200_000
        assert budget.used_tokens == 0
        assert budget.remaining == 200_000
        assert budget.utilization_target == 0.40
