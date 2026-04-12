"""Policy engine -- evaluates tool calls against the current configuration."""

from __future__ import annotations

from typing import Any

from devharness.core.models import (
    ApprovalMode,
    PolicyDecision,
    ThreadConfig,
    ToolCategory,
)

from .modes import evaluate_mode
from .rules import PolicyRule, apply_rules, default_rules


class PolicyEngine:
    """Evaluate whether a tool call should be allowed, denied, or held for approval.

    The engine works in two stages:

    1. **Mode evaluation** -- the thread's ``ApprovalMode`` determines the
       baseline decision (auto-approve, require approval, deny).
    2. **Rule evaluation** -- custom ``PolicyRule`` instances can override
       the baseline by denying specific patterns.
    """

    def __init__(self, extra_rules: list[PolicyRule] | None = None) -> None:
        self._rules: list[PolicyRule] = list(default_rules())
        if extra_rules:
            self._rules.extend(extra_rules)

    # -----------------------------------------------------------------

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        config: ThreadConfig,
        *,
        tool_category: ToolCategory | None = None,
    ) -> PolicyDecision:
        """Return a PolicyDecision for the given tool call."""

        # --- denied / allowed lists ---
        if config.denied_tools and tool_name in config.denied_tools:
            return PolicyDecision(
                allowed=False,
                mode=config.approval_mode,
                reason=f"Tool '{tool_name}' is in the denied tools list.",
            )

        if config.allowed_tools is not None and tool_name not in config.allowed_tools:
            return PolicyDecision(
                allowed=False,
                mode=config.approval_mode,
                reason=f"Tool '{tool_name}' is not in the allowed tools list.",
            )

        # --- mode-based evaluation ---
        category = tool_category or ToolCategory.EXECUTE
        decision = evaluate_mode(config.approval_mode, tool_name, category)

        # If the mode already denied or requires approval, return early.
        if not decision.allowed or decision.requires_user_approval:
            return decision

        # --- custom rules ---
        rule_result = apply_rules(self._rules, tool_name, arguments, category)
        if rule_result is not None:
            return rule_result

        return decision
