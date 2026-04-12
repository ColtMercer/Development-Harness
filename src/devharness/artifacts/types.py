"""Artifact type helpers and convenience factories.

This module provides helper functions for creating commonly-used artifact
types with sensible defaults.
"""

from __future__ import annotations

from typing import Any

from devharness.core.models import Artifact, ArtifactKind


def make_patch(
    thread_id: str,
    name: str,
    diff_content: str,
    *,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """Create a patch artifact from a unified diff string."""
    return Artifact(
        thread_id=thread_id,
        turn_id=turn_id,
        kind=ArtifactKind.PATCH,
        name=name,
        content=diff_content,
        metadata=metadata or {},
    )


def make_plan(
    thread_id: str,
    name: str,
    plan_text: str,
    *,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """Create a plan artifact."""
    return Artifact(
        thread_id=thread_id,
        turn_id=turn_id,
        kind=ArtifactKind.PLAN,
        name=name,
        content=plan_text,
        metadata=metadata or {},
    )


def make_report(
    thread_id: str,
    name: str,
    body: str,
    *,
    turn_id: str | None = None,
    kind: ArtifactKind = ArtifactKind.REPORT,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """Create a report artifact (also usable for summaries and test reports)."""
    return Artifact(
        thread_id=thread_id,
        turn_id=turn_id,
        kind=kind,
        name=name,
        content=body,
        metadata=metadata or {},
    )


def make_screenshot(
    thread_id: str,
    name: str,
    file_path: str,
    *,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """Create a screenshot artifact pointing to an on-disk image file."""
    return Artifact(
        thread_id=thread_id,
        turn_id=turn_id,
        kind=ArtifactKind.SCREENSHOT,
        name=name,
        file_path=file_path,
        metadata=metadata or {},
    )


def make_log(
    thread_id: str,
    name: str,
    log_content: str,
    *,
    turn_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Artifact:
    """Create a log artifact."""
    return Artifact(
        thread_id=thread_id,
        turn_id=turn_id,
        kind=ArtifactKind.LOG,
        name=name,
        content=log_content,
        metadata=metadata or {},
    )


def is_text_artifact(artifact: Artifact) -> bool:
    """Return True if the artifact's content is text-based (not a file reference)."""
    return artifact.kind not in (ArtifactKind.SCREENSHOT,)


def is_binary_artifact(artifact: Artifact) -> bool:
    """Return True if the artifact is stored as a file on disk."""
    return artifact.file_path is not None
