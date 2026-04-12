"""Approval-mode evaluation helpers."""

from __future__ import annotations

from devharness.core.models import ApprovalMode, PolicyDecision, ToolCategory


def evaluate_mode(
    mode: ApprovalMode,
    tool_name: str,
    category: ToolCategory,
) -> PolicyDecision:
    """Return the baseline PolicyDecision for *mode* and *category*."""

    if mode == ApprovalMode.FULL_TRUST:
        return _full_trust(tool_name, category)
    if mode == ApprovalMode.AUTO_APPROVE_SAFE:
        return _auto_approve_safe(tool_name, category)
    if mode == ApprovalMode.APPROVAL_REQUIRED:
        return _approval_required(tool_name, category)
    if mode == ApprovalMode.READ_ONLY:
        return _read_only(tool_name, category)
    if mode == ApprovalMode.WORKSPACE_WRITE:
        return _workspace_write(tool_name, category)

    # Fallback -- require approval for unknown modes
    return PolicyDecision(
        allowed=True,
        mode=mode,
        reason="Unknown mode; requiring user approval.",
        requires_user_approval=True,
    )


# ---------------------------------------------------------------------------
# Per-mode helpers
# ---------------------------------------------------------------------------


def _full_trust(tool_name: str, category: ToolCategory) -> PolicyDecision:
    """All tool calls are auto-approved."""
    return PolicyDecision(
        allowed=True,
        mode=ApprovalMode.FULL_TRUST,
        reason="Full trust mode: auto-approved.",
    )


def _auto_approve_safe(tool_name: str, category: ToolCategory) -> PolicyDecision:
    """READ tools are auto-approved; WRITE and EXECUTE require user approval."""
    if category == ToolCategory.READ:
        return PolicyDecision(
            allowed=True,
            mode=ApprovalMode.AUTO_APPROVE_SAFE,
            reason="Read-only tool auto-approved.",
        )
    return PolicyDecision(
        allowed=True,
        mode=ApprovalMode.AUTO_APPROVE_SAFE,
        reason=f"Tool category '{category}' requires user approval.",
        requires_user_approval=True,
    )


def _approval_required(tool_name: str, category: ToolCategory) -> PolicyDecision:
    """Every tool call requires explicit user approval."""
    return PolicyDecision(
        allowed=True,
        mode=ApprovalMode.APPROVAL_REQUIRED,
        reason="Approval required for all tool calls.",
        requires_user_approval=True,
    )


def _read_only(tool_name: str, category: ToolCategory) -> PolicyDecision:
    """Only READ tools are allowed; everything else is denied."""
    if category == ToolCategory.READ:
        return PolicyDecision(
            allowed=True,
            mode=ApprovalMode.READ_ONLY,
            reason="Read-only mode: read tool auto-approved.",
        )
    return PolicyDecision(
        allowed=False,
        mode=ApprovalMode.READ_ONLY,
        reason=f"Read-only mode: '{category}' tools are denied.",
    )


def _workspace_write(tool_name: str, category: ToolCategory) -> PolicyDecision:
    """READ and WRITE tools are auto-approved; EXECUTE requires approval."""
    if category in (ToolCategory.READ, ToolCategory.WRITE):
        return PolicyDecision(
            allowed=True,
            mode=ApprovalMode.WORKSPACE_WRITE,
            reason=f"Workspace-write mode: '{category}' tool auto-approved.",
        )
    return PolicyDecision(
        allowed=True,
        mode=ApprovalMode.WORKSPACE_WRITE,
        reason="Workspace-write mode: execute tools require user approval.",
        requires_user_approval=True,
    )
