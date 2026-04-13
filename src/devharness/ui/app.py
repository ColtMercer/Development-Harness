"""Starlette + HTMX web UI application.

A lightweight dashboard for managing the harness. No JS build step --
uses HTMX for server-rendered reactivity and SSE for real-time updates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from devharness.core.config import HarnessConfig
from devharness.core.runtime import Runtime

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"


def create_ui_routes(runtime: Runtime, config: HarnessConfig) -> list:
    """Create web UI routes for the Starlette app."""
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, Response
    from starlette.routing import Route, Mount
    from starlette.staticfiles import StaticFiles
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

    def render(template_name: str, **context: Any) -> HTMLResponse:
        template = env.get_template(template_name)
        return HTMLResponse(template.render(**context))

    # Track running tasks so we don't block the request
    _running_threads: dict[str, str] = {}  # thread_id -> prompt

    async def dashboard(request: Request) -> Response:
        threads = await runtime.list_threads()
        projects = await runtime._storage.list_projects()
        return render(
            "dashboard.html",
            threads=threads,
            projects=projects,
            config=config,
        )

    async def new_thread_page(request: Request) -> Response:
        skill_names = [s.name for s in runtime._skills.list_skills()]
        return render("new_thread.html", config=config, available_skills=skill_names)

    async def create_thread(request: Request) -> Response:
        from starlette.responses import RedirectResponse
        from devharness.core.models import ThreadConfig
        import anyio

        form = await request.form()
        prompt = form.get("prompt", "").strip()
        if not prompt:
            return RedirectResponse("/threads/new", status_code=303)

        agent = form.get("agent_backend", config.default_agent_backend)
        approval = form.get("approval_mode", config.default_approval_mode)
        skills_str = form.get("skills", "")
        skills = [s.strip() for s in skills_str.split(",") if s.strip()] if skills_str else []
        workspace = form.get("workspace_root", ".")
        verification = form.get("verification_enabled") == "true"

        thread_config = ThreadConfig(
            agent_backend=agent,
            approval_mode=approval,
            skills=skills,
            workspace_root=workspace,
            verification_enabled=verification,
        )
        thread = await runtime.create_thread(thread_config)
        _running_threads[thread.id] = prompt

        # Run the turn in background so we don't block the redirect
        async def _run_in_background() -> None:
            try:
                await runtime.run_turn(thread.id, prompt)
            except Exception as e:
                logger.error("Thread %s failed: %s", thread.id, e)
            finally:
                _running_threads.pop(thread.id, None)

        # Fire and forget using anyio
        from anyio import create_task_group, sleep

        # We can't fire-and-forget with structured concurrency, so we
        # start the task and redirect immediately. The task runs to completion
        # on its own. For a production system we'd use a proper task queue.
        import asyncio
        asyncio.get_event_loop().create_task(_run_in_background())

        return RedirectResponse(f"/threads/{thread.id}/live", status_code=303)

    async def thread_live(request: Request) -> Response:
        thread_id = request.path_params["thread_id"]
        thread = await runtime.get_thread(thread_id)
        events = await runtime._storage.load_events(thread_id)
        prompt = _running_threads.get(thread_id, "")
        if not prompt and thread.turns:
            prompt = thread.turns[0].user_input
        return render(
            "thread_running.html",
            thread=thread,
            events=events,
            prompt=prompt,
            config=config,
        )

    async def thread_status_fragment(request: Request) -> Response:
        """HTMX polling endpoint -- returns just the status fragment."""
        thread_id = request.path_params["thread_id"]
        thread = await runtime.get_thread(thread_id)
        events = await runtime._storage.load_events(thread_id)

        if thread.status.value == "running":
            return HTMLResponse(
                f'<div hx-get="/threads/{thread_id}/status" hx-trigger="every 3s" hx-swap="outerHTML">'
                f'<article aria-busy="true"><p>Agent is working...</p>'
                f'<p><small>Events so far: {len(events)}</small></p></article></div>'
            )
        else:
            # Done -- redirect to the full page to show final results
            return HTMLResponse(
                f'<script>window.location.href="/threads/{thread_id}/live";</script>'
            )

    async def thread_detail(request: Request) -> Response:
        thread_id = request.path_params["thread_id"]
        thread = await runtime.get_thread(thread_id)
        events = await runtime._storage.load_events(thread_id)
        artifacts = await runtime._storage.load_artifacts(thread_id)
        return render(
            "thread.html",
            thread=thread,
            events=events,
            artifacts=artifacts,
        )

    async def approvals_page(request: Request) -> Response:
        threads = await runtime.list_threads()
        pending = [t for t in threads if t.pending_approval]
        return render("approvals.html", pending_threads=pending)

    async def approve_action(request: Request) -> Response:
        form = await request.form()
        thread_id = form["thread_id"]
        approval_id = form["approval_id"]
        action = form["action"]
        await runtime.resolve_approval(
            thread_id, approval_id, action == "approve"
        )
        # HTMX: return updated approvals list
        threads = await runtime.list_threads()
        pending = [t for t in threads if t.pending_approval]
        return render("approvals.html", pending_threads=pending)

    async def skills_page(request: Request) -> Response:
        skills = runtime._skills.list_skills()
        return render("skills.html", skills=skills)

    async def observe_page(request: Request) -> Response:
        threads = await runtime.list_threads()
        return render("observe.html", threads=threads)

    async def _load_credentials_status() -> dict[str, bool]:
        """Check which credentials are set (without revealing values)."""
        from devharness.core.config import CREDENTIAL_KEYS
        status = {}
        for key, meta in CREDENTIAL_KEYS.items():
            val = await runtime._storage.load_credential(
                None, meta["provider"], meta["key_name"]
            )
            status[key] = val is not None and len(val) > 0
        return status

    async def settings_page(request: Request) -> Response:
        cred_status = await _load_credentials_status()
        return render("settings.html", config=config, cred_status=cred_status)

    async def settings_save(request: Request) -> Response:
        from devharness.core.config import CREDENTIAL_KEYS, SETTINGS_KEYS, save_config_to_db

        form = await request.form()
        saved_keys = []

        # Process all form fields
        for key in list(SETTINGS_KEYS.keys()) + list(CREDENTIAL_KEYS.keys()):
            value = form.get(key, "")
            if not value:
                continue
            # For credentials, skip if the placeholder wasn't changed
            if key in CREDENTIAL_KEYS and value.startswith("••••"):
                continue
            try:
                await save_config_to_db(key, value, runtime._storage)
                saved_keys.append(key)
            except ValueError:
                pass

        # Reload config from DB to reflect changes
        from devharness.core.config import load_config_from_db
        nonlocal config
        config = await load_config_from_db(config, runtime._storage)

        cred_status = await _load_credentials_status()
        return render(
            "settings.html", config=config, cred_status=cred_status,
            saved=saved_keys if saved_keys else None,
        )

    routes = [
        Route("/", dashboard),
        Route("/threads/new", new_thread_page, methods=["GET"]),
        Route("/threads/new", create_thread, methods=["POST"]),
        Route("/threads/{thread_id}/live", thread_live),
        Route("/threads/{thread_id}/status", thread_status_fragment),
        Route("/threads/{thread_id}", thread_detail),
        Route("/approvals", approvals_page),
        Route("/approvals/action", approve_action, methods=["POST"]),
        Route("/skills", skills_page),
        Route("/observe", observe_page),
        Route("/settings", settings_page, methods=["GET"]),
        Route("/settings", settings_save, methods=["POST"]),
    ]

    if STATIC_DIR.exists():
        routes.append(Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static"))

    return routes
