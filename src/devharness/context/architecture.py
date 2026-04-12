"""Tiered context architecture targeting 40% utilization.

The context architecture divides information into three tiers:

- **Tier 1 (Hot)**: Always loaded -- system prompt, project constitution.
- **Tier 2 (Warm)**: Task-activated -- skill prompts, relevant docs, recent
  observation summaries.
- **Tier 3 (Cold)**: On-demand -- accessed via tools during execution, never
  pre-loaded into the context window.

The goal is to keep context utilization around the 40% sweet spot so the
model has room to reason without being overwhelmed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from devharness.context.budget import estimate_tokens, format_observation_summary, trim_to_budget
from devharness.context.loader import SkillRegistry, load_context_files, load_skill_prompts
from devharness.core.models import AgentContext, ContextBudget, Thread

if TYPE_CHECKING:
    from devharness.core.models import ObservationSummary

logger = logging.getLogger(__name__)

# Default system prompt fragment (~60 lines target for Tier 1)
_DEFAULT_SYSTEM_PROMPT = (
    "You are an autonomous development agent managed by the Development Harness.\n"
    "Follow the project constitution and architectural rules.\n"
    "Use tools to interact with the codebase -- do not guess at file contents.\n"
    "After making changes, verify correctness via the available verification tools.\n"
    "Report progress and issues clearly."
)


class ContextArchitecture:
    """Build tiered agent context within a token budget.

    Parameters
    ----------
    system_prompt:
        Base system prompt (Tier 1). Falls back to a built-in default.
    context_files:
        Paths to project context files (CLAUDE.md, AGENTS.md, etc.) resolved
        relative to the thread's workspace root.
    skill_registry:
        Optional skill registry for loading skill prompts (Tier 2).
    max_tokens:
        Maximum context window size in tokens.
    utilization_target:
        Target utilization ratio (default 0.40).
    """

    def __init__(
        self,
        *,
        system_prompt: str | None = None,
        context_files: list[str] | None = None,
        skill_registry: SkillRegistry | None = None,
        max_tokens: int = 200_000,
        utilization_target: float = 0.40,
    ) -> None:
        self._system_prompt = system_prompt or _DEFAULT_SYSTEM_PROMPT
        self._context_files = context_files or []
        self._skill_registry = skill_registry
        self._max_tokens = max_tokens
        self._utilization_target = utilization_target

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def build_context(
        self,
        thread: Thread,
        task: str,
        *,
        observation_summary: ObservationSummary | None = None,
    ) -> AgentContext:
        """Assemble an AgentContext for *task* within the token budget.

        Tiers are loaded in order; Tier 2 content is trimmed if the budget
        target would be exceeded.  Tier 3 is never pre-loaded.
        """
        budget = ContextBudget(
            max_tokens=self._max_tokens,
            utilization_target=self._utilization_target,
        )

        target_tokens = int(budget.max_tokens * budget.utilization_target)

        # --- Tier 1: Hot (always loaded) ---
        system_prompt = self._system_prompt
        if thread.config.system_prompt_override:
            system_prompt = thread.config.system_prompt_override

        tier1_parts: list[str] = [system_prompt]

        # Load project context files (constitution, CLAUDE.md, etc.)
        workspace_root = thread.config.workspace_root
        project_docs = load_context_files(self._context_files, workspace_root)
        tier1_parts.extend(project_docs)

        tier1_text = "\n\n".join(tier1_parts)
        budget.tier1_tokens = estimate_tokens(tier1_text)

        # --- Tier 2: Warm (task-activated) ---
        tier2_items: list[str] = []

        # Task instruction
        tier2_items.append(f"Current task: {task}")

        # Skill prompts
        if self._skill_registry is not None and thread.config.skills:
            skill_prompts = load_skill_prompts(
                thread.config.skills, self._skill_registry
            )
            tier2_items.extend(skill_prompts)

        # Observation summary
        obs_text: str | None = None
        if observation_summary is not None:
            obs_text = format_observation_summary(observation_summary)
            tier2_items.append(obs_text)

        # Trim Tier 2 to fit budget (oldest / least relevant first)
        remaining_for_tier2 = max(0, target_tokens - budget.tier1_tokens)
        tier2_items = trim_to_budget(tier2_items, remaining_for_tier2)

        budget.tier2_tokens = sum(estimate_tokens(t) for t in tier2_items)

        # --- Tier 3: Cold (on-demand, not pre-loaded) ---
        # Tier 3 contributes 0 tokens -- content is fetched via tools at
        # runtime when the agent decides it needs more information.
        budget.tier3_tokens = 0

        # --- Assemble ---
        return AgentContext(
            system_prompt=tier1_text,
            instructions=tier2_items,
            observation_summary=obs_text,
            token_usage=budget,
        )
