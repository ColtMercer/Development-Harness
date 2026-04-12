"""Token budget utilities for context management.

Provides rough token estimation, budget-aware trimming, and formatting
of observation summaries for injection into agent context.
"""

from __future__ import annotations

from devharness.core.models import ObservationSummary


def estimate_tokens(text: str) -> int:
    """Rough token estimate -- approximately 4 characters per token.

    This is intentionally conservative (over-estimates) so that we stay
    within budget rather than exceeding it.
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def trim_to_budget(texts: list[str], max_tokens: int) -> list[str]:
    """Keep texts that fit within *max_tokens*, dropping oldest first.

    Texts are assumed to be ordered oldest-first.  We walk from the end
    (newest) backwards, accumulating until the budget is exhausted, then
    return the kept texts in their original order.
    """
    if max_tokens <= 0:
        return []

    kept: list[tuple[int, str]] = []
    used = 0

    for idx in range(len(texts) - 1, -1, -1):
        cost = estimate_tokens(texts[idx])
        if used + cost <= max_tokens:
            kept.append((idx, texts[idx]))
            used += cost
        else:
            break

    # Restore original order.
    kept.sort(key=lambda pair: pair[0])
    return [t for _, t in kept]


def format_observation_summary(summary: ObservationSummary) -> str:
    """Format an ObservationSummary for injection into agent context."""
    lines: list[str] = []
    lines.append("--- Observation Summary ---")
    lines.append(f"Thread: {summary.thread_id}  Turn: {summary.turn_id}")

    if summary.new_errors or summary.new_warnings:
        lines.append(
            f"New issues: {summary.new_errors} error(s), "
            f"{summary.new_warnings} warning(s)"
        )

    # Process status
    if summary.process_status:
        lines.append("Process status:")
        for name, status in summary.process_status.items():
            lines.append(f"  {name}: {status}")

    # Test summary
    if summary.test_summary is not None:
        ts = summary.test_summary
        lines.append(
            f"Tests: {ts.passed}/{ts.total} passed, "
            f"{ts.failed} failed, {ts.errored} errored"
        )
        if ts.coverage_pct is not None:
            lines.append(f"Coverage: {ts.coverage_pct:.1f}%")
        for failure in ts.failures:
            lines.append(f"  FAIL: {failure.test_name} - {failure.assertion_message}")

    # Endpoint summary
    if summary.endpoint_summary is not None:
        es = summary.endpoint_summary
        lines.append(
            f"Endpoints: {es.healthy_count} healthy, "
            f"{es.unhealthy_count} unhealthy"
        )
        for ep in es.endpoints:
            if not ep.is_healthy:
                lines.append(f"  UNHEALTHY: {ep.url} - {ep.error or 'unknown'}")

    # Individual observations (warnings and above)
    notable = [
        obs
        for obs in summary.observations
        if obs.severity in ("warning", "error", "critical")
    ]
    if notable:
        lines.append("Notable observations:")
        for obs in notable:
            lines.append(f"  [{obs.severity.upper()}] {obs.title}: {obs.details}")

    lines.append("--- End Observation Summary ---")
    return "\n".join(lines)
