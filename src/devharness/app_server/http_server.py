"""HTTP/SSE server using Starlette.

Serves both the JSON-RPC API and the web UI.
Events are streamed via Server-Sent Events (SSE).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from devharness.app_server.jsonrpc import JsonRpcDispatcher, JsonRpcRequest
from devharness.app_server.protocol import register_methods
from devharness.core.config import HarnessConfig
from devharness.core.event_bus import EventBus
from devharness.core.runtime import Runtime

logger = logging.getLogger(__name__)


def create_app(runtime: Runtime, config: HarnessConfig) -> Any:
    """Create the Starlette ASGI application."""
    try:
        from starlette.applications import Starlette
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.routing import Route
    except ImportError:
        raise ImportError(
            "Server dependencies not installed. Run: pip install devharness[server]"
        )

    # Set up JSON-RPC dispatcher
    dispatcher = JsonRpcDispatcher()
    register_methods(dispatcher, runtime)

    async def rpc_endpoint(request: Request) -> JSONResponse:
        """Handle JSON-RPC requests over HTTP POST."""
        body = await request.json()
        rpc_request = JsonRpcRequest(**body)
        response = await dispatcher.dispatch(rpc_request)
        return JSONResponse(response.model_dump(mode="json"))

    async def health_endpoint(request: Request) -> JSONResponse:
        """Health check."""
        return JSONResponse({"status": "ok", "version": "0.1.0"})

    async def threads_api(request: Request) -> JSONResponse:
        """REST-style threads listing."""
        project_id = request.query_params.get("project_id")
        threads = await runtime.list_threads(project_id)
        return JSONResponse([t.model_dump(mode="json") for t in threads])

    async def thread_detail_api(request: Request) -> JSONResponse:
        """REST-style thread detail."""
        thread_id = request.path_params["thread_id"]
        thread = await runtime.get_thread(thread_id)
        return JSONResponse(thread.model_dump(mode="json"))

    # Try to mount the web UI
    routes = [
        Route("/api/rpc", rpc_endpoint, methods=["POST"]),
        Route("/api/health", health_endpoint),
        Route("/api/threads", threads_api),
        Route("/api/threads/{thread_id}", thread_detail_api),
    ]

    try:
        from devharness.ui.app import create_ui_routes

        ui_routes = create_ui_routes(runtime, config)
        routes.extend(ui_routes)
    except ImportError:
        logger.info("Web UI not available (missing jinja2 or templates)")

    app = Starlette(routes=routes)
    return app
