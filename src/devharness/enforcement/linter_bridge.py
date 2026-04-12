"""Bridge between linter output and agent-readable correction prompts.

Parses linter output and generates structured corrections that include
the specific instruction needed to fix the violation.
"""

from __future__ import annotations

import json
import re


def parse_ruff_output(output: str) -> list[dict]:
    """Parse ruff check output (JSON or text format) into structured issues."""
    try:
        return json.loads(output)
    except (json.JSONDecodeError, ValueError):
        pass

    # Fall back to text parsing
    issues = []
    for line in output.split("\n"):
        match = re.match(
            r"(.+?):(\d+):(\d+): (\w+) (.+)", line
        )
        if match:
            issues.append({
                "filename": match.group(1),
                "location": {"row": int(match.group(2)), "column": int(match.group(3))},
                "code": match.group(4),
                "message": match.group(5),
            })
    return issues


def format_correction_prompt(issues: list[dict], max_issues: int = 10) -> str:
    """Format linter issues as an agent-readable correction prompt."""
    if not issues:
        return ""

    lines = [f"Found {len(issues)} linter issue(s). Fix the following:"]
    for issue in issues[:max_issues]:
        filename = issue.get("filename", "?")
        row = issue.get("location", {}).get("row", "?")
        code = issue.get("code", "?")
        message = issue.get("message", "?")
        lines.append(f"  {filename}:{row} [{code}] {message}")

    if len(issues) > max_issues:
        lines.append(f"  ... and {len(issues) - max_issues} more")

    return "\n".join(lines)
