# Tools System

Tools are executable capabilities available to the agent. Each tool has a name, description, category, JSON Schema for its parameters, and an async `execute()` method. Tools are registered in the `ToolRegistry` and made available to the agent based on the thread configuration and policy engine.

---

## Tool Model

Every tool implements the `BaseTool` abstract class:

```python
class BaseTool(ABC):
    name: str                    # Unique identifier
    description: str             # Human-readable description for the LLM
    category: ToolCategory       # read, write, or execute

    async def execute(self, **kwargs) -> ToolResult:
        """Run the tool with the given arguments."""

    def get_input_schema(self) -> dict:
        """Return JSON Schema describing accepted parameters."""
```

### Tool Categories

| Category | Meaning | Policy Implications |
|----------|---------|-------------------|
| `read` | Inspects state, no side effects | Auto-approved in most modes |
| `write` | Modifies files | Requires approval in `auto_approve_safe`; denied in `read_only` |
| `execute` | Runs processes, arbitrary commands | Requires approval in most modes except `full_trust` |

The category directly determines how the policy engine treats the tool call. Set it correctly.

### ToolResult

```python
class ToolResult(BaseModel):
    output: str              # The tool's output text
    is_error: bool = False   # Whether the tool encountered an error
    metadata: dict = {}      # Additional structured data
    truncated: bool = False  # Whether output was truncated
```

---

## Built-in Tools

### shell

**Category:** execute

Runs a shell command in the workspace directory.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `command` | string | Yes | The shell command to execute |

### file_read

**Category:** read

Reads the contents of a file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Path to the file (relative to workspace root) |

### file_write

**Category:** write

Writes content to a file.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Path to the file |
| `content` | string | Yes | Content to write |

### search

**Category:** read

Searches for text patterns in files.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `query` | string | Yes | Search pattern |

### git_status

**Category:** read

Shows the current git status of the workspace.

### test_runner

**Category:** execute

Runs the project's test suite.

### lint_runner

**Category:** execute

Runs the project's linter.

### diff_tool

**Category:** read

Shows file diffs (staged, unstaged, or between revisions).

---

## Tool Registry

The `ToolRegistry` is the central catalogue of available tools.

### Registering a Tool Class

```python
from devharness.tools.registry import ToolRegistry
from devharness.tools.base import BaseTool
from devharness.core.models import ToolCategory, ToolResult

class MyTool(BaseTool):
    name = "my_tool"
    description = "Performs a custom operation"
    category = ToolCategory.READ

    async def execute(self, query: str, limit: int = 10) -> ToolResult:
        result = perform_operation(query, limit)
        return self._ok(result)

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["query"],
        }

registry = ToolRegistry()
registry.register(MyTool())
```

### Registering a Function

The `@registry.tool()` decorator wraps a plain function as a tool. The JSON Schema is auto-generated from the function's type hints.

```python
from devharness.tools.registry import ToolRegistry
from devharness.core.models import ToolCategory, ToolResult

registry = ToolRegistry()

@registry.tool("count_lines", ToolCategory.READ, "Count lines in a file")
async def count_lines(path: str) -> ToolResult:
    with open(path) as f:
        count = sum(1 for _ in f)
    return ToolResult(output=f"{count} lines")
```

Type hints are converted to JSON Schema via the `fn_to_json_schema()` utility. Supported types:

| Python Type | JSON Schema Type |
|-------------|-----------------|
| `str` | `string` |
| `int` | `integer` |
| `float` | `number` |
| `bool` | `boolean` |
| `Path` | `string` |
| `list[X]` | `array` with items |
| `dict[K, V]` | `object` with additionalProperties |
| `X \| None` | Schema for `X` (optional) |
| `Annotated[X, ...]` | Schema for `X` with metadata |

Parameters without defaults are marked as `required`. Parameters with defaults include the default in the schema.

### Querying Tools

```python
# Get a tool by name
tool = registry.get("shell")

# Get tool category
category = registry.get_category("file_write")  # ToolCategory.WRITE

# List all tools
all_tools = registry.list_tools()

# Get LLM-ready definitions (filtered)
definitions = registry.get_definitions_for_llm(
    allowed=["file_read", "file_write", "search"],
    denied=["shell"],
)
```

### LLM Definition Format

`to_llm_definition()` returns:

```json
{
    "name": "file_read",
    "description": "Read the contents of a file",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string"}
        },
        "required": ["path"]
    }
}
```

This format is compatible with Anthropic's tool use API and similar interfaces.

---

## Convenience Methods

`BaseTool` provides helper methods for building results:

### `_ok(output, **meta)`

Build a successful result:

```python
return self._ok("Operation completed successfully", items_processed=42)
```

### `_error(message, **meta)`

Build an error result:

```python
return self._error("File not found: config.yaml")
```

### `_truncated(output, max_bytes)`

Truncate large output and flag it:

```python
return self._truncated(huge_output, max_bytes=50_000)
```

If the output fits within `max_bytes`, returns a normal `_ok()` result. Otherwise, truncates and sets `truncated=True`.

---

## Tool Filtering

Tools are filtered at two levels:

### Thread-Level Filtering

`ThreadConfig` specifies `allowed_tools` and `denied_tools`:

```python
config = ThreadConfig(
    allowed_tools=["file_read", "search"],  # only these tools available
    denied_tools=["shell"],                  # these blocked even if in allowed
)
```

### Policy-Level Filtering

The `PolicyEngine` evaluates each tool call against the approval mode and custom rules. Even if a tool is in the allowed list, a policy rule can deny specific invocations based on arguments.

---

## Creating a Custom Tool: Full Example

```python
from devharness.tools.base import BaseTool
from devharness.core.models import ToolCategory, ToolResult
import httpx

class FetchUrlTool(BaseTool):
    name = "fetch_url"
    description = "Fetch the content of a URL and return the response body"
    category = ToolCategory.READ

    async def execute(self, url: str, timeout: int = 30) -> ToolResult:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=timeout)
                response.raise_for_status()
                # Truncate large responses
                return self._truncated(response.text, max_bytes=100_000)
        except httpx.HTTPStatusError as e:
            return self._error(f"HTTP {e.response.status_code}: {e.response.reason_phrase}")
        except httpx.RequestError as e:
            return self._error(f"Request failed: {e}")

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds",
                    "default": 30,
                },
            },
            "required": ["url"],
        }
```
