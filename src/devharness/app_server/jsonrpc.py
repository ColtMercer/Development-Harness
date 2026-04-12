"""JSON-RPC message types and dispatch.

The harness uses JSON-RPC 2.0 over stdio and HTTP for its protocol.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class JsonRpcRequest(BaseModel):
    """JSON-RPC 2.0 request."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


class JsonRpcError(BaseModel):
    """JSON-RPC 2.0 error."""

    code: int
    message: str
    data: Any = None


class JsonRpcResponse(BaseModel):
    """JSON-RPC 2.0 response."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    result: Any = None
    error: JsonRpcError | None = None


class JsonRpcNotification(BaseModel):
    """JSON-RPC 2.0 notification (no id, no response expected)."""

    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class JsonRpcDispatcher:
    """Dispatch JSON-RPC requests to handler functions."""

    def __init__(self) -> None:
        self._handlers: dict[str, Any] = {}

    def register(self, method: str, handler: Any) -> None:
        self._handlers[method] = handler

    async def dispatch(self, request: JsonRpcRequest) -> JsonRpcResponse:
        """Dispatch a request and return a response."""
        handler = self._handlers.get(request.method)

        if handler is None:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(
                    code=METHOD_NOT_FOUND,
                    message=f"Method not found: {request.method}",
                ),
            )

        try:
            result = await handler(**request.params)
            return JsonRpcResponse(id=request.id, result=result)
        except TypeError as e:
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(
                    code=INVALID_PARAMS,
                    message=f"Invalid params: {e}",
                ),
            )
        except Exception as e:
            logger.exception("Handler error for %s", request.method)
            return JsonRpcResponse(
                id=request.id,
                error=JsonRpcError(
                    code=INTERNAL_ERROR,
                    message=str(e),
                ),
            )
