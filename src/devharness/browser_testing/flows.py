"""Load browser test flow definitions from YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from devharness.core.models import (
    BrowserAssertion,
    BrowserTestFlow,
    BrowserTestStep,
)


def load_flow_from_file(path: str) -> BrowserTestFlow:
    """Load a browser test flow from a YAML file."""
    content = Path(path).read_text()
    data = yaml.safe_load(content)
    return _parse_flow(data)


def load_flows_from_directory(directory: str) -> list[BrowserTestFlow]:
    """Load all browser test flows from a directory."""
    flows = []
    dir_path = Path(directory)
    if not dir_path.exists():
        return flows

    for yaml_file in sorted(dir_path.glob("*.yaml")) + sorted(dir_path.glob("*.yml")):
        try:
            flows.append(load_flow_from_file(str(yaml_file)))
        except Exception:
            pass  # skip malformed files

    return flows


def _parse_flow(data: dict) -> BrowserTestFlow:
    """Parse a flow dictionary into a BrowserTestFlow model."""
    steps = [
        BrowserTestStep(
            action=s["action"],
            selector=s.get("selector"),
            value=s.get("value"),
            name=s.get("name"),
            timeout=s.get("timeout", 5000),
        )
        for s in data.get("steps", [])
    ]

    assertions = [
        BrowserAssertion(
            type=a["type"],
            value=a.get("value"),
            selector=a.get("selector"),
        )
        for a in data.get("assertions", [])
    ]

    return BrowserTestFlow(
        name=data["name"],
        url=data["url"],
        steps=steps,
        assertions=assertions,
        viewport_width=data.get("viewport_width", 1280),
        viewport_height=data.get("viewport_height", 720),
    )
