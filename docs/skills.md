# Skills System

Skills are the primary unit of composition in the Development Harness. Each skill bundles a persona-level system prompt with the tools and verifiers that persona needs. Multiple skills can be activated simultaneously, and their prompts are concatenated into the agent's context.

---

## What a Skill Contains

A skill is a directory with two files:

```
skills/
  python-web/
    manifest.yaml     # Metadata: name, tools, verifiers, hooks, context files
    prompt.md          # System prompt text
```

### manifest.yaml

```yaml
name: python-web
version: "1.0.0"
description: "Python web application development"
system_prompt: ""  # used if prompt.md is absent
tools:
  - shell
  - file_read
  - file_write
  - test_runner
  - lint_runner
verifiers:
  - pytest
  - ruff
hooks:
  post_tool_call:
    script: "pytest --tb=short -q 2>&1 && exit 0 || { pytest --tb=short -q 2>&1; exit 2; }"
context_files:
  - CLAUDE.md
  - docs/ARCHITECTURE.md
config_schema: {}  # optional JSON Schema for skill-specific config
```

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique skill identifier |
| `version` | No | Semantic version string (default: `"0.1.0"`) |
| `description` | No | Human-readable description |
| `system_prompt` | No | Inline system prompt (fallback if no `prompt.md`) |
| `tools` | No | Tool names this skill requires |
| `verifiers` | No | Verifier names this skill registers |
| `hooks` | No | Hook configurations keyed by event name |
| `context_files` | No | Paths to context files loaded into Tier 2 |
| `config_schema` | No | JSON Schema for skill-specific configuration |

### prompt.md

The system prompt for this skill. This is the persona-level instruction set that shapes how the agent behaves when this skill is active.

```markdown
You are a Python web application developer working with FastAPI and SQLAlchemy.

## Practices
- Use Pydantic models for all request/response schemas
- Write async endpoint handlers
- Use dependency injection for database sessions
- Write tests for every endpoint using pytest + httpx

## Architecture
- Routes in `src/app/routes/`
- Models in `src/app/models/`
- Services in `src/app/services/`
- Tests in `tests/`

## Rules
- Never commit without running tests
- Always run `ruff format` before committing
- Keep functions under 50 lines
```

---

## How Skills Are Loaded

### Filesystem Discovery

The `SkillLoader` walks configured directories looking for subdirectories that contain `manifest.yaml`:

```python
from devharness.skills.loader import SkillLoader
from pathlib import Path

skills = SkillLoader.discover([Path("skills"), Path("~/.devharness/skills")])
```

1. For each base directory, iterate over subdirectories.
2. If a subdirectory contains `manifest.yaml`, parse it.
3. If `prompt.md` exists in the same directory, use it as the system prompt. Otherwise, use the `system_prompt` field from the manifest.
4. Return a list of `BaseSkill` instances.

Directories that fail to load are logged as warnings and skipped. A malformed skill does not prevent other skills from loading.

### Skill Registry

Loaded skills are registered with the `SkillRegistry`:

```python
from devharness.skills.registry import SkillRegistry

registry = SkillRegistry()
for skill in skills:
    registry.register(skill)
```

Skills are keyed by their manifest name. Registering a skill with the same name as an existing one replaces it (useful for reloading during development).

---

## How Skills Are Activated

### Per-Thread Activation

Skills are activated per-thread via the `ThreadConfig`:

```python
from devharness.core.models import ThreadConfig

config = ThreadConfig(skills=["python-web", "testing"])
```

Or via CLI:

```bash
harness run "fix the login bug" --skill python-web --skill testing
```

### Prompt Assembly

When building context for a turn, the `ContextArchitecture` calls:

```python
combined = registry.get_combined_system_prompt(["python-web", "testing"])
```

This concatenates each skill's system prompt, separated by `---`. The combined prompt is placed in Tier 2 (warm context), subject to token budget trimming.

### Tool and Verifier Resolution

When a skill specifies tools and verifiers, those names are used to:

1. Filter the tool registry (via `allowed_tools` in `AgentConstraints`).
2. Activate specific verifiers in the verification pipeline.

This means a skill can declare exactly which tools the agent should use, preventing tool sprawl.

---

## Creating a Skill

### Step 1: Create the Directory

```bash
mkdir -p skills/my-skill
```

### Step 2: Write the Manifest

```yaml
# skills/my-skill/manifest.yaml
name: my-skill
version: "0.1.0"
description: "My custom skill for specific tasks"
tools:
  - file_read
  - file_write
  - shell
  - search
verifiers: []
context_files:
  - docs/my-guide.md
```

### Step 3: Write the Prompt

```markdown
# skills/my-skill/prompt.md

You are a specialist in [domain]. Follow these practices:

- [Practice 1]
- [Practice 2]
- [Practice 3]

## File Structure
- [Where things go]

## Rules
- [Hard constraints]
```

### Step 4: Test It

```bash
harness run "do a thing with my-skill" --skill my-skill
```

### Step 5: Verify Loading

```bash
harness skills
```

Output:

```
  my-skill v0.1.0 - My custom skill for specific tasks
```

---

## Programmatic Skills

For skills that need dynamic behavior (computed prompts, runtime tool discovery), subclass `BaseSkill`:

```python
from devharness.skills.base import BaseSkill
from devharness.core.models import SkillManifest

class DynamicSkill(BaseSkill):
    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            name="dynamic-skill",
            version="1.0.0",
            description="A programmatic skill",
            tools=["file_read", "shell"],
        )

    def get_system_prompt(self) -> str:
        # Can compute this dynamically
        return f"You are working on project X. Today is {date.today()}."
```

Register directly:

```python
registry.register(DynamicSkill())
```

---

## Skill Composition

Multiple skills can be active simultaneously. Their prompts are concatenated with `---` separators. Design skills to be composable:

- Avoid conflicting instructions between skills.
- Use skills for orthogonal concerns (one for the domain, one for testing, one for deployment).
- Keep individual skill prompts concise -- they consume Tier 2 context budget.

Example composition:

```bash
harness run "add authentication" --skill python-web --skill security --skill testing
```

The agent receives all three prompts and follows the combined instructions.

---

## Skill Configuration

Skills can define a `config_schema` in their manifest for skill-specific settings. The schema is a JSON Schema object. Configuration values are passed through the skill activation mechanism.

This enables parameterized skills (e.g., a "deployment" skill that takes a target environment as config).

---

## Built-in Skills

The `skills/builtin/` directory contains skills shipped with the harness. They serve as reference implementations and can be activated out of the box.

To list all available skills:

```bash
harness skills
```
