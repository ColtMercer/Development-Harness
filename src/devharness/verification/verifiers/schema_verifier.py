"""Verifier that validates JSON and YAML files for syntactic correctness."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml

from devharness.core.models import Thread, Turn, VerificationResult
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)

_JSON_SUFFIXES = {".json", ".jsonl"}
_YAML_SUFFIXES = {".yaml", ".yml"}


class SchemaVerifier(BaseVerifier):
    """Validates that JSON and YAML files in the workspace are syntactically valid.

    This verifier walks the workspace (skipping hidden dirs, node_modules,
    and __pycache__) and attempts to parse every ``.json``, ``.yaml``, and
    ``.yml`` file.
    """

    @property
    def name(self) -> str:
        return "schema_verifier"

    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        workspace = Path(thread.config.workspace_root)
        errors: list[str] = []
        checked = 0

        for path in workspace.rglob("*"):
            if not path.is_file():
                continue
            # Skip common noise directories.
            parts = path.relative_to(workspace).parts
            if any(
                p.startswith(".") or p in ("node_modules", "__pycache__", ".git")
                for p in parts
            ):
                continue

            suffix = path.suffix.lower()
            if suffix in _JSON_SUFFIXES:
                checked += 1
                try:
                    json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    errors.append(f"{path.relative_to(workspace)}: {exc}")
            elif suffix in _YAML_SUFFIXES:
                checked += 1
                try:
                    yaml.safe_load(path.read_text(encoding="utf-8"))
                except Exception as exc:
                    errors.append(f"{path.relative_to(workspace)}: {exc}")

        if errors:
            return VerificationResult(
                verifier_name=self.name,
                passed=False,
                message=f"{len(errors)} schema error(s) found",
                details={"errors": errors, "files_checked": checked},
            )

        return VerificationResult(
            verifier_name=self.name,
            passed=True,
            message=f"All {checked} JSON/YAML files are valid",
            details={"files_checked": checked},
        )
