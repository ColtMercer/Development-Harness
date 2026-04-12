"""Exception hierarchy for the harness.

Every harness-specific error inherits from HarnessError so callers can
catch broadly or narrowly as needed.
"""


class HarnessError(Exception):
    """Base exception for all devharness errors."""


# --- Thread lifecycle ---


class ThreadNotFoundError(HarnessError):
    """Raised when a thread ID does not exist in storage."""


class ThreadAlreadyRunningError(HarnessError):
    """Raised when attempting to start a turn on a thread that is already running."""


# --- Tools ---


class ToolNotFoundError(HarnessError):
    """Raised when a requested tool name is not registered."""


class ToolExecutionError(HarnessError):
    """Raised when a tool fails during execution."""


class ToolTimeoutError(ToolExecutionError):
    """Raised when a tool exceeds its timeout."""


# --- Approvals ---


class ApprovalDeniedError(HarnessError):
    """Raised when a tool call is denied by policy or user."""


class ApprovalTimeoutError(HarnessError):
    """Raised when an approval request times out waiting for response."""


# --- Policy ---


class PolicyViolationError(HarnessError):
    """Raised when an action violates a policy rule."""


# --- Verification ---


class VerificationFailedError(HarnessError):
    """Raised when verification fails and repair attempts are exhausted."""


# --- Skills ---


class SkillNotFoundError(HarnessError):
    """Raised when a requested skill name is not registered."""


class SkillLoadError(HarnessError):
    """Raised when a skill directory cannot be loaded."""


# --- Storage ---


class StorageError(HarnessError):
    """Raised on persistence failures (read/write/delete)."""


# --- Agent ---


class AgentError(HarnessError):
    """Raised when an agent backend fails."""


class AgentNotFoundError(AgentError):
    """Raised when a requested agent backend is not registered."""


# --- Configuration ---


class ConfigError(HarnessError):
    """Raised on configuration loading or validation errors."""


# --- Protocol ---


class ProtocolError(HarnessError):
    """Raised on JSON-RPC or protocol-level errors."""


# --- Replay ---


class ReplayError(HarnessError):
    """Raised when replaying a thread encounters inconsistencies."""


# --- Memory ---


class MemoryError(HarnessError):
    """Raised on knowledge graph / memory subsystem errors."""


class MemoryUnavailableError(MemoryError):
    """Raised when the memory backend (Neo4j/Obsidian) is not reachable.

    The harness should degrade gracefully -- this is never fatal.
    """


# --- Browser testing ---


class BrowserTestError(HarnessError):
    """Raised when a browser test flow fails to execute."""
