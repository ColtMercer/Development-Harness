"""Block Kit message builders for Slack notifications.

Each builder returns a dict with ``"blocks"`` (list of Block Kit block
dicts) and ``"text"`` (plain-text fallback for push notifications).
"""

from __future__ import annotations

from typing import Any

from devharness.core.models import ApprovalRequest, BrowserTestResult


def build_approval_message(request: ApprovalRequest) -> dict[str, Any]:
    """Build an interactive approval message with Approve / Deny buttons.

    Parameters
    ----------
    request:
        The pending approval request.

    Returns
    -------
    dict
        Block Kit payload with ``blocks`` and ``text`` keys.
    """
    return {
        "text": f"Approval needed: {request.tool_name}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "Approval Required",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Tool:*\n`{request.tool_name}`",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Category:*\n{request.category.value}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Reason:*\n{request.reason or 'No reason provided'}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Arguments:*\n```{_truncate(str(request.arguments), 500)}```",
                },
            },
            {
                "type": "actions",
                "block_id": f"approval_{request.id}",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "approve",
                        "value": request.id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Deny"},
                        "style": "danger",
                        "action_id": "deny",
                        "value": request.id,
                    },
                ],
            },
        ],
    }


def build_notification(title: str, body: str, thread_id: str) -> dict[str, Any]:
    """Build a simple notification message.

    Parameters
    ----------
    title:
        The notification headline.
    body:
        Descriptive body text (Markdown supported).
    thread_id:
        The harness thread ID for context.

    Returns
    -------
    dict
        Block Kit payload.
    """
    return {
        "text": f"{title}: {body[:100]}",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": title},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _truncate(body, 2000),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Thread: `{thread_id}`",
                    }
                ],
            },
        ],
    }


def build_browser_test_failure(result: BrowserTestResult) -> dict[str, Any]:
    """Build a notification for a browser test failure.

    Parameters
    ----------
    result:
        The failed browser test result.

    Returns
    -------
    dict
        Block Kit payload.
    """
    fields = [
        {"type": "mrkdwn", "text": f"*Flow:*\n`{result.flow_name}`"},
        {
            "type": "mrkdwn",
            "text": f"*Steps:*\n{result.steps_completed}/{result.steps_total}",
        },
    ]

    blocks: list[dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "Browser Test Failed"},
        },
        {"type": "section", "fields": fields},
    ]

    if result.failure_reason:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Failure reason:*\n```{_truncate(result.failure_reason, 1000)}```",
                },
            }
        )

    if result.failure_step is not None:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Failed at step {result.failure_step}",
                    }
                ],
            }
        )

    if result.console_errors:
        error_text = "\n".join(result.console_errors[:5])
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Console errors:*\n```{_truncate(error_text, 500)}```",
                },
            }
        )

    return {
        "text": f"Browser test failed: {result.flow_name}",
        "blocks": blocks,
    }


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to *max_len* characters, appending an ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
