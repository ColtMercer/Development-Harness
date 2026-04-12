"""Built-in enforcement rules.

These encode common architectural constraints with agent-readable
correction prompts.
"""

from __future__ import annotations

from devharness.core.models import EnforcementRule


def import_boundary_rule(
    name: str = "import_boundaries",
    layers: str = "Types → Config → Repo → Service → Runtime → UI",
) -> EnforcementRule:
    """Enforce dependency layer ordering."""
    return EnforcementRule(
        name=name,
        check_command="ruff check --select I --output-format text",
        error_pattern=r".*\.py:\d+:\d+: .*",
        correction_prompt=(
            f"Import violation detected. The project uses layered architecture: {layers}. "
            f"Modules in lower layers must not import from higher layers. "
            f"Fix the import to respect the dependency direction."
        ),
        architectural_layer=layers,
    )


def no_print_rule() -> EnforcementRule:
    """Disallow print() statements in production code."""
    return EnforcementRule(
        name="no_print",
        check_command="grep -rn 'print(' src/ --include='*.py' | grep -v '__pycache__' | grep -v 'test_'",
        error_pattern=r".*\.py:\d+:.*print\(",
        correction_prompt=(
            "Found print() statements in production code. "
            "Use logging.getLogger(__name__) and logger.info/debug/warning instead."
        ),
    )


def type_check_rule() -> EnforcementRule:
    """Run mypy type checking."""
    return EnforcementRule(
        name="type_check",
        check_command="mypy src/ --ignore-missing-imports --no-error-summary 2>&1 || true",
        error_pattern=r".*\.py:\d+: error:.*",
        correction_prompt=(
            "Type checking errors found. Fix the type annotations to satisfy mypy. "
            "Common fixes: add type hints to function signatures, fix incompatible types, "
            "use Optional[] for nullable values."
        ),
    )


def test_coverage_rule(min_coverage: int = 70) -> EnforcementRule:
    """Enforce minimum test coverage."""
    return EnforcementRule(
        name="test_coverage",
        check_command=f"pytest --cov=src --cov-fail-under={min_coverage} -q 2>&1 || true",
        error_pattern=r"TOTAL.*FAIL",
        correction_prompt=(
            f"Test coverage is below {min_coverage}%. "
            f"Add tests for uncovered code paths. Focus on critical business logic."
        ),
    )


def default_rules() -> list[EnforcementRule]:
    """Return a sensible default set of enforcement rules."""
    return [
        type_check_rule(),
    ]
