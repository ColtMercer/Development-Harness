"""Endpoint observer -- probes HTTP endpoints for health.

Checks configured URLs, measures response times, captures error responses.
"""

from __future__ import annotations

import logging

import httpx

from devharness.core.models import (
    EndpointStatus,
    EndpointSummary,
    Observation,
    ObservationSeverity,
    Thread,
    Turn,
)
from devharness.observers.base import BaseObserver

logger = logging.getLogger(__name__)


class EndpointObserver(BaseObserver):
    """Probe HTTP endpoints and report health status."""

    name = "endpoint"

    def __init__(
        self,
        urls: list[dict] | None = None,
        timeout: float = 10.0,
    ) -> None:
        # Each url dict: {"url": str, "expected_status": int, "method": str}
        self._urls = urls or []
        self._timeout = timeout
        self._running = False

    async def observe(self, thread: Thread, turn: Turn | None = None) -> list[Observation]:
        """Probe all configured endpoints."""
        if not self._urls:
            return []

        observations: list[Observation] = []
        statuses: list[EndpointStatus] = []

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for url_config in self._urls:
                url = url_config["url"]
                expected = url_config.get("expected_status", 200)
                method = url_config.get("method", "GET")

                status = await self._probe(client, url, method, expected)
                statuses.append(status)

                if not status.is_healthy:
                    observations.append(
                        Observation(
                            observer_name=self.name,
                            thread_id=thread.id,
                            turn_id=turn.id if turn else None,
                            severity=ObservationSeverity.ERROR,
                            title=f"{method} {url} - {status.status_code or 'unreachable'}",
                            details=status.error or "",
                            data={
                                "url": url,
                                "status_code": status.status_code,
                                "response_time_ms": status.response_time_ms,
                                "error": status.error,
                            },
                        )
                    )

        # Build endpoint summary
        healthy = sum(1 for s in statuses if s.is_healthy)
        unhealthy = len(statuses) - healthy

        if statuses:
            summary = EndpointSummary(
                endpoints=statuses,
                healthy_count=healthy,
                unhealthy_count=unhealthy,
            )
            # Attach summary to first observation or create info observation
            if not observations:
                observations.append(
                    Observation(
                        observer_name=self.name,
                        thread_id=thread.id,
                        turn_id=turn.id if turn else None,
                        severity=ObservationSeverity.INFO,
                        title=f"Endpoints: {healthy}/{len(statuses)} healthy",
                        data={"endpoint_summary": summary.model_dump(mode="json")},
                    )
                )

        return observations

    async def _probe(
        self, client: httpx.AsyncClient, url: str, method: str, expected: int
    ) -> EndpointStatus:
        """Probe a single endpoint."""
        try:
            response = await client.request(method, url)
            is_healthy = response.status_code == expected
            error = None
            if not is_healthy:
                # Capture error response body (truncated)
                error = response.text[:1000]
            return EndpointStatus(
                url=url,
                status_code=response.status_code,
                response_time_ms=response.elapsed.total_seconds() * 1000
                if response.elapsed
                else None,
                is_healthy=is_healthy,
                error=error,
            )
        except httpx.RequestError as e:
            return EndpointStatus(
                url=url,
                is_healthy=False,
                error=f"{type(e).__name__}: {e}",
            )

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
