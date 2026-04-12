"""Architectural fitness verifier -- enforces dependency-layer rules.

This verifier checks that modules respect a configurable layering
policy.  For example, ``core`` should never import from ``ui``, and
``tools`` should not import from ``agents``.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

from devharness.core.models import Thread, Turn, VerificationResult
from devharness.verification.base import BaseVerifier

logger = logging.getLogger(__name__)

# Default layer rules: a mapping of module prefixes to the set of
# prefixes they are *not* allowed to import from.
_DEFAULT_FORBIDDEN: dict[str, list[str]] = {
    "core": ["agents", "tools", "ui", "integrations", "skills"],
    "tools": ["agents", "ui", "integrations"],
    "verification": ["agents", "ui", "integrations"],
    "skills": ["agents", "ui", "integrations"],
}


class ArchitectureVerifier(BaseVerifier):
    """Checks that Python imports respect architectural layering rules.

    Parameters
    ----------
    package_root:
        The top-level Python package name (e.g. ``"devharness"``).
    forbidden:
        Mapping of layer name to list of layers it must not import from.
        Falls back to ``_DEFAULT_FORBIDDEN`` if not provided.
    """

    def __init__(
        self,
        package_root: str = "devharness",
        forbidden: dict[str, list[str]] | None = None,
    ) -> None:
        self._package_root = package_root
        self._forbidden = forbidden if forbidden is not None else dict(_DEFAULT_FORBIDDEN)

    @property
    def name(self) -> str:
        return "architecture_verifier"

    async def verify(self, thread: Thread, turn: Turn) -> VerificationResult:
        workspace = Path(thread.config.workspace_root)
        violations: list[str] = []
        checked = 0

        src_root = workspace / "src" / self._package_root
        if not src_root.is_dir():
            src_root = workspace / self._package_root
        if not src_root.is_dir():
            return VerificationResult(
                verifier_name=self.name,
                passed=True,
                message=f"Package root {self._package_root} not found; skipping",
            )

        for py_file in src_root.rglob("*.py"):
            rel = py_file.relative_to(src_root)
            layer = rel.parts[0] if len(rel.parts) > 1 else None
            if layer is None or layer not in self._forbidden:
                continue

            checked += 1
            forbidden_layers = self._forbidden[layer]
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            except SyntaxError:
                continue

            for node in ast.walk(tree):
                module: str | None = None
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module = alias.name
                        self._check_import(
                            module, layer, forbidden_layers, py_file, src_root, violations
                        )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module
                    self._check_import(
                        module, layer, forbidden_layers, py_file, src_root, violations
                    )

        if violations:
            return VerificationResult(
                verifier_name=self.name,
                passed=False,
                message=f"{len(violations)} architectural violation(s)",
                details={"violations": violations, "files_checked": checked},
            )

        return VerificationResult(
            verifier_name=self.name,
            passed=True,
            message=f"No architectural violations in {checked} files",
            details={"files_checked": checked},
        )

    def _check_import(
        self,
        module: str,
        source_layer: str,
        forbidden_layers: list[str],
        py_file: Path,
        src_root: Path,
        violations: list[str],
    ) -> None:
        """Append a violation string if *module* belongs to a forbidden layer."""
        prefix = f"{self._package_root}."
        if not module.startswith(prefix):
            return
        remainder = module[len(prefix):]
        target_layer = remainder.split(".")[0]
        if target_layer in forbidden_layers:
            rel = py_file.relative_to(src_root)
            violations.append(
                f"{rel}: {source_layer} imports from {target_layer} ({module})"
            )
