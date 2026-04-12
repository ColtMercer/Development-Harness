"""Tests for devharness.policies.engine.PolicyEngine."""

from __future__ import annotations

from devharness.core.models import ApprovalMode, ThreadConfig, ToolCategory
from devharness.policies.engine import PolicyEngine


def _make_config(
    mode: ApprovalMode = ApprovalMode.AUTO_APPROVE_SAFE,
    allowed_tools: list[str] | None = None,
    denied_tools: list[str] | None = None,
) -> ThreadConfig:
    return ThreadConfig(
        approval_mode=mode,
        allowed_tools=allowed_tools,
        denied_tools=denied_tools,
    )


class TestFullTrustMode:
    def test_read_tool_allowed(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_read", {}, _make_config(ApprovalMode.FULL_TRUST),
            tool_category=ToolCategory.READ,
        )
        assert decision.allowed is True
        assert decision.requires_user_approval is False

    def test_write_tool_allowed(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_write", {}, _make_config(ApprovalMode.FULL_TRUST),
            tool_category=ToolCategory.WRITE,
        )
        assert decision.allowed is True
        assert decision.requires_user_approval is False

    def test_execute_tool_allowed(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "shell", {}, _make_config(ApprovalMode.FULL_TRUST),
            tool_category=ToolCategory.EXECUTE,
        )
        assert decision.allowed is True


class TestAutoApproveSafeMode:
    def test_read_auto_approved(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_read", {}, _make_config(ApprovalMode.AUTO_APPROVE_SAFE),
            tool_category=ToolCategory.READ,
        )
        assert decision.allowed is True
        assert decision.requires_user_approval is False

    def test_write_requires_approval(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_write", {}, _make_config(ApprovalMode.AUTO_APPROVE_SAFE),
            tool_category=ToolCategory.WRITE,
        )
        assert decision.allowed is True
        assert decision.requires_user_approval is True

    def test_execute_requires_approval(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "shell", {}, _make_config(ApprovalMode.AUTO_APPROVE_SAFE),
            tool_category=ToolCategory.EXECUTE,
        )
        assert decision.allowed is True
        assert decision.requires_user_approval is True


class TestApprovalRequiredMode:
    def test_read_requires_approval(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_read", {}, _make_config(ApprovalMode.APPROVAL_REQUIRED),
            tool_category=ToolCategory.READ,
        )
        assert decision.allowed is True
        assert decision.requires_user_approval is True

    def test_write_requires_approval(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_write", {}, _make_config(ApprovalMode.APPROVAL_REQUIRED),
            tool_category=ToolCategory.WRITE,
        )
        assert decision.requires_user_approval is True

    def test_execute_requires_approval(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "shell", {}, _make_config(ApprovalMode.APPROVAL_REQUIRED),
            tool_category=ToolCategory.EXECUTE,
        )
        assert decision.requires_user_approval is True


class TestReadOnlyMode:
    def test_read_allowed(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_read", {}, _make_config(ApprovalMode.READ_ONLY),
            tool_category=ToolCategory.READ,
        )
        assert decision.allowed is True

    def test_write_denied(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "file_write", {}, _make_config(ApprovalMode.READ_ONLY),
            tool_category=ToolCategory.WRITE,
        )
        assert decision.allowed is False

    def test_execute_denied(self) -> None:
        engine = PolicyEngine()
        decision = engine.evaluate(
            "shell", {}, _make_config(ApprovalMode.READ_ONLY),
            tool_category=ToolCategory.EXECUTE,
        )
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# Denied / allowed tool lists
# ---------------------------------------------------------------------------


class TestDeniedAllowedLists:
    def test_denied_tool(self) -> None:
        engine = PolicyEngine()
        config = _make_config(denied_tools=["shell"])
        decision = engine.evaluate("shell", {}, config, tool_category=ToolCategory.EXECUTE)
        assert decision.allowed is False
        assert "denied" in decision.reason.lower()

    def test_allowed_tool_not_in_list(self) -> None:
        engine = PolicyEngine()
        config = _make_config(allowed_tools=["file_read"])
        decision = engine.evaluate(
            "shell", {}, config, tool_category=ToolCategory.EXECUTE
        )
        assert decision.allowed is False
        assert "not in the allowed" in decision.reason.lower()

    def test_allowed_tool_in_list(self) -> None:
        engine = PolicyEngine()
        config = _make_config(
            mode=ApprovalMode.FULL_TRUST,
            allowed_tools=["file_read"],
        )
        decision = engine.evaluate(
            "file_read", {}, config, tool_category=ToolCategory.READ
        )
        assert decision.allowed is True

    def test_denied_takes_precedence(self) -> None:
        engine = PolicyEngine()
        config = _make_config(
            allowed_tools=["shell"],
            denied_tools=["shell"],
        )
        decision = engine.evaluate(
            "shell", {}, config, tool_category=ToolCategory.EXECUTE
        )
        # denied_tools is checked first in the engine
        assert decision.allowed is False


# ---------------------------------------------------------------------------
# Built-in rules (dangerous patterns)
# ---------------------------------------------------------------------------


class TestBuiltinRules:
    def test_deny_env_file_write(self) -> None:
        engine = PolicyEngine()
        config = _make_config(mode=ApprovalMode.FULL_TRUST)
        decision = engine.evaluate(
            "file_write",
            {"path": "src/.env"},
            config,
            tool_category=ToolCategory.WRITE,
        )
        assert decision.allowed is False

    def test_deny_sudo_command(self) -> None:
        engine = PolicyEngine()
        config = _make_config(mode=ApprovalMode.FULL_TRUST)
        decision = engine.evaluate(
            "shell",
            {"command": "sudo rm -rf /"},
            config,
            tool_category=ToolCategory.EXECUTE,
        )
        assert decision.allowed is False

    def test_allow_safe_command(self) -> None:
        engine = PolicyEngine()
        config = _make_config(mode=ApprovalMode.FULL_TRUST)
        decision = engine.evaluate(
            "shell",
            {"command": "ls -la"},
            config,
            tool_category=ToolCategory.EXECUTE,
        )
        assert decision.allowed is True
