"""Codebase onboarding -- scan, analyze, and configure the harness for a project."""

from devharness.onboarding.scanner import CodebaseProfile, CodebaseScanner
from devharness.onboarding.context_generator import generate_agents_md, generate_harness_config
from devharness.onboarding.hook_generator import generate_hooks

__all__ = [
    "CodebaseProfile",
    "CodebaseScanner",
    "generate_agents_md",
    "generate_harness_config",
    "generate_hooks",
]
