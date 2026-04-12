"""Generate ObservationSummary from raw observations.

The summary is a structured report injected into the agent's context
after each turn. Key principle: success is silent, failures are highlighted.
"""

from __future__ import annotations

from devharness.core.models import (
    Observation,
    ObservationSeverity,
    ObservationSummary,
    TestSummary,
)


def build_observation_summary(
    thread_id: str,
    turn_id: str,
    observations: list[Observation],
) -> ObservationSummary:
    """Build a structured summary from raw observations."""
    new_errors = sum(
        1 for o in observations if o.severity == ObservationSeverity.ERROR
    )
    new_warnings = sum(
        1 for o in observations if o.severity == ObservationSeverity.WARNING
    )

    # Extract process status from process observer observations
    process_status: dict[str, str] = {}
    for obs in observations:
        if obs.observer_name == "process" and "process_name" in obs.data:
            process_status[obs.data["process_name"]] = obs.data.get("status", "unknown")

    # Extract test summary if test observer ran
    test_summary = None
    for obs in observations:
        if obs.observer_name == "test" and "test_summary" in obs.data:
            test_summary = TestSummary(**obs.data["test_summary"])
            break

    return ObservationSummary(
        thread_id=thread_id,
        turn_id=turn_id,
        observations=observations,
        process_status=process_status,
        test_summary=test_summary,
        new_errors=new_errors,
        new_warnings=new_warnings,
    )


def format_summary_for_agent(summary: ObservationSummary) -> str:
    """Format an ObservationSummary as text for injection into agent context.

    Follows the 'success silent, failures only' principle. Only includes
    noteworthy observations.
    """
    lines: list[str] = []
    lines.append("[OBSERVATION REPORT - since your last action]")

    # Process status (only if issues)
    for name, status in summary.process_status.items():
        if status != "running":
            lines.append(f"- Process: {name} - {status}")

    # Test summary (only if failures)
    if summary.test_summary and summary.test_summary.failed > 0:
        ts = summary.test_summary
        lines.append(
            f"- Tests: {ts.passed} passed, {ts.failed} failed, {ts.errored} errored"
        )
        for failure in ts.failures[:5]:  # limit to 5 failures
            lines.append(f"  - {failure.test_name}: {failure.assertion_message}")
            if failure.file_path:
                lines.append(f"    at {failure.file_path}:{failure.line_number or '?'}")

    # Error/warning observations
    error_obs = [
        o
        for o in summary.observations
        if o.severity in (ObservationSeverity.ERROR, ObservationSeverity.CRITICAL)
    ]
    for obs in error_obs[:10]:  # limit
        lines.append(f"- {obs.observer_name}: {obs.title}")
        if obs.details:
            # Truncate long details
            detail_lines = obs.details.split("\n")[:3]
            for dl in detail_lines:
                lines.append(f"  {dl[:200]}")

    # If nothing noteworthy, say so briefly
    if len(lines) == 1:
        lines.append("- No issues detected.")

    return "\n".join(lines)
