"""CLI entry point for the Development Harness.

Usage:
    harness serve          Start the harness server (HTTP + Web UI)
    harness run            Run a prompt in a new thread
    harness resume         Resume a paused thread
    harness threads        List threads
    harness events         Stream/inspect events
    harness approve        Approve/deny pending requests
    harness replay         Replay a run
    harness skills         List/inspect skills
    harness artifacts      List/inspect artifacts
    harness verify         Run verification
    harness observe        Show observation summary
    harness hooks          List/manage hooks
    harness init           Initialize project harness
    harness browser-test   Run browser test flows
"""

from __future__ import annotations

import click

from devharness.core.config import load_config


@click.group()
@click.option("--storage-dir", type=click.Path(), help="Storage directory path")
@click.option("--log-level", type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]))
@click.option("--verbose", "-v", is_flag=True, help="Show harness internal logs")
@click.pass_context
def cli(ctx: click.Context, storage_dir: str | None, log_level: str | None, verbose: bool) -> None:
    """Development Harness - Control plane for coding agents."""
    import logging

    ctx.ensure_object(dict)
    config = load_config()
    if storage_dir:
        from pathlib import Path
        config.storage_dir = Path(storage_dir)
    if log_level:
        config.log_level = log_level

    # Suppress internal harness logs for CLI commands unless --verbose.
    # The structured JSON log lines are useful for debugging but noisy for normal use.
    if not verbose:
        logging.getLogger("devharness").setLevel(logging.WARNING)

    ctx.obj["config"] = config


@cli.command()
@click.option("--host", default=None, help="Server host")
@click.option("--port", default=None, type=int, help="Server port")
@click.pass_context
def serve(ctx: click.Context, host: str | None, port: int | None) -> None:
    """Start the harness server with web UI."""
    import anyio

    config = ctx.obj["config"]
    if host:
        config.server_host = host
    if port:
        config.server_port = port

    async def _serve() -> None:
        from devharness.bootstrap import bootstrap, shutdown
        import logging as _logging
        # Suppress noisy aiosqlite debug logs during serve
        _logging.getLogger("aiosqlite").setLevel(_logging.WARNING)

        runtime = await bootstrap(config)
        click.echo(f"Harness server starting on http://{config.server_host}:{config.server_port}")

        try:
            from devharness.app_server.http_server import create_app
            import uvicorn
        except ImportError:
            click.echo("Server dependencies not installed. Run: pip install devharness[server]")
            await shutdown(runtime)
            return

        app = create_app(runtime, config)
        server_config = uvicorn.Config(
            app,
            host=config.server_host,
            port=config.server_port,
            log_level=config.log_level.lower(),
        )
        server = uvicorn.Server(server_config)
        try:
            await server.serve()
        finally:
            await shutdown(runtime)

    anyio.run(_serve)


@cli.command()
@click.argument("prompt")
@click.option("--agent", default=None, help="Agent backend (claude-code, codex)")
@click.option("--project", default=None, help="Project ID or name")
@click.option("--skill", multiple=True, help="Skills to activate")
@click.option("--approval-mode", type=click.Choice(["full_trust", "auto_approve_safe", "approval_required", "read_only"]))
@click.pass_context
def run(ctx: click.Context, prompt: str, agent: str | None, project: str | None, skill: tuple, approval_mode: str | None) -> None:
    """Run a prompt in a new thread."""
    import anyio

    config = ctx.obj["config"]

    async def _run() -> None:
        from devharness.bootstrap import bootstrap, shutdown
        from devharness.core.models import ThreadConfig

        runtime = await bootstrap(config)

        thread_config = ThreadConfig(
            agent_backend=agent or config.default_agent_backend,
            skills=list(skill),
        )
        if approval_mode:
            thread_config.approval_mode = approval_mode
        if project:
            thread_config.project_id = project

        thread = await runtime.create_thread(thread_config)
        click.echo(f"Thread created: {thread.id}")

        turn = await runtime.run_turn(thread.id, prompt)

        if turn.assistant_response:
            click.echo(f"\n{turn.assistant_response}")
        if turn.error:
            click.echo(f"\nError: {turn.error}", err=True)
        if turn.verification and not turn.verification.all_passed:
            click.echo("\nVerification issues:")
            for r in turn.verification.results:
                status = "PASS" if r.passed else "FAIL"
                click.echo(f"  [{status}] {r.verifier_name}: {r.message}")

        click.echo(f"\nThread: {thread.id} | Status: {thread.status}")
        await shutdown(runtime)

    anyio.run(_run)


@cli.command()
@click.option("--project", default=None, help="Filter by project")
@click.option("--status", default=None, help="Filter by status")
@click.pass_context
def threads(ctx: click.Context, project: str | None, status: str | None) -> None:
    """List threads."""
    import anyio

    config = ctx.obj["config"]

    async def _list() -> None:
        from devharness.bootstrap import bootstrap, shutdown

        runtime = await bootstrap(config)
        thread_list = await runtime.list_threads(project)

        if status:
            thread_list = [t for t in thread_list if t.status == status]

        if not thread_list:
            click.echo("No threads found.")
            return

        for t in thread_list:
            turns = len(t.turns)
            click.echo(f"  {t.id}  [{t.status}]  turns={turns}  created={t.created_at.isoformat()[:19]}")

        await shutdown(runtime)

    anyio.run(_list)


@cli.command()
@click.argument("thread_id")
@click.pass_context
def replay(ctx: click.Context, thread_id: str) -> None:
    """Replay events from a thread."""
    import anyio

    config = ctx.obj["config"]

    async def _replay() -> None:
        from devharness.bootstrap import bootstrap, shutdown

        runtime = await bootstrap(config)

        async for event in runtime.replay_thread(thread_id):
            click.echo(f"  [{event.timestamp.isoformat()[:19]}] {event.kind} {event.data}")

        await shutdown(runtime)

    anyio.run(_replay)


@cli.command()
@click.argument("thread_id")
@click.argument("approval_id")
@click.option("--approve/--deny", default=True)
@click.option("--reason", default="")
@click.pass_context
def approve(ctx: click.Context, thread_id: str, approval_id: str, approve: bool, reason: str) -> None:
    """Approve or deny a pending request."""
    import anyio

    config = ctx.obj["config"]

    async def _approve() -> None:
        from devharness.bootstrap import bootstrap, shutdown

        runtime = await bootstrap(config)
        await runtime.resolve_approval(thread_id, approval_id, approve, reason)
        action = "approved" if approve else "denied"
        click.echo(f"Approval {approval_id} {action}")
        await shutdown(runtime)

    anyio.run(_approve)


@cli.command()
@click.pass_context
def skills(ctx: click.Context) -> None:
    """List available skills."""
    import anyio

    config = ctx.obj["config"]

    async def _skills() -> None:
        from devharness.bootstrap import bootstrap, shutdown

        runtime = await bootstrap(config)
        skill_list = runtime._skills.list_skills()

        if not skill_list:
            click.echo("No skills loaded.")
            return

        for s in skill_list:
            click.echo(f"  {s.name} v{s.version} - {s.description}")

        await shutdown(runtime)

    anyio.run(_skills)


@cli.command()
@click.argument("thread_id")
@click.pass_context
def artifacts(ctx: click.Context, thread_id: str) -> None:
    """List artifacts for a thread."""
    import anyio

    config = ctx.obj["config"]

    async def _artifacts() -> None:
        from devharness.bootstrap import bootstrap, shutdown

        runtime = await bootstrap(config)
        art_list = await runtime._artifacts.list_for_thread(thread_id)

        if not art_list:
            click.echo("No artifacts found.")
            return

        for a in art_list:
            click.echo(f"  {a.id} [{a.kind}] {a.name} ({a.created_at.isoformat()[:19]})")

        await shutdown(runtime)

    anyio.run(_artifacts)


@cli.command()
@click.option("--template", default=None, help="Template name (python-web, python-cli, generic)")
@click.option("--skip-scan", is_flag=True, help="Skip codebase scanning")
@click.pass_context
def init(ctx: click.Context, template: str | None, skip_scan: bool) -> None:
    """Initialize harness in an existing project.

    Scans the codebase to detect languages, frameworks, test runners, and
    build tools. Generates context files, configures hooks and observers,
    and stores everything in the database.
    """
    import anyio
    from pathlib import Path

    config = ctx.obj["config"]

    async def _init() -> None:
        from devharness.bootstrap import bootstrap, shutdown

        runtime = await bootstrap(config)

        # Create .gitignore for the harness directory
        storage_dir = config.storage_dir
        storage_dir.mkdir(parents=True, exist_ok=True)
        gitignore = storage_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# Ignore everything in this directory\n*\n!.gitignore\n")

        if not skip_scan:
            try:
                from devharness.onboarding.scanner import CodebaseScanner
                from devharness.onboarding.context_generator import generate_agents_md, generate_harness_config
                from devharness.onboarding.hook_generator import generate_hooks

                click.echo("Scanning codebase...")
                scanner = CodebaseScanner(workspace_root=".")
                profile = scanner.scan()

                click.echo(f"\nDetected:")
                click.echo(f"  Language:    {profile.primary_language}")
                click.echo(f"  Frameworks:  {', '.join(profile.frameworks) or 'none detected'}")
                click.echo(f"  Tests:       {', '.join(profile.test_frameworks) or 'none detected'}")
                click.echo(f"  Package mgr: {', '.join(profile.package_managers) or 'none detected'}")
                click.echo(f"  Project type: {'web app' if profile.web_app else 'API' if profile.api_app else 'CLI' if profile.cli_app else 'library' if profile.library else 'unknown'}")
                click.echo(f"  Size:        {profile.estimated_size}")

                # Generate AGENTS.md
                agents_md = generate_agents_md(profile)
                agents_path = Path("AGENTS.md")
                if not agents_path.exists():
                    agents_path.write_text(agents_md)
                    click.echo(f"\n  Created AGENTS.md with project-specific instructions")
                else:
                    click.echo(f"\n  AGENTS.md already exists, skipping")

                # Generate hooks
                hooks = generate_hooks(profile)
                hooks_dir = storage_dir / "hooks"
                hooks_dir.mkdir(exist_ok=True)
                for hook_name, hook_script in hooks.items():
                    hook_path = hooks_dir / f"{hook_name}.sh"
                    hook_path.write_text(hook_script)
                    hook_path.chmod(0o755)
                click.echo(f"  Generated {len(hooks)} hook scripts in {hooks_dir}/")

                # Store config in DB
                harness_config = generate_harness_config(profile)
                for key, value in harness_config.items():
                    await runtime._storage.set_setting(key, str(value))
                click.echo(f"  Stored {len(harness_config)} settings in database")

            except ImportError:
                click.echo("  Onboarding module not found, creating basic setup")
            except Exception as e:
                click.echo(f"  Scan error: {e}, creating basic setup")

        click.echo(f"\nHarness initialized at {config.storage_dir}/")
        click.echo(f"\nNext steps:")
        click.echo(f"  harness serve               Start the web UI at http://localhost:{config.server_port}")
        click.echo(f"  harness config set <k> <v>  Configure settings")
        click.echo(f"  harness config set-credential anthropic.api_key <key>")
        click.echo(f"  harness run \"your prompt\"    Start working")

        await shutdown(runtime)

    anyio.run(_init)


# --- Config management ---

@cli.group()
def config() -> None:
    """Manage harness configuration (stored in database)."""
    pass


@config.command("list")
@click.pass_context
def config_list(ctx: click.Context) -> None:
    """List all configurable settings."""
    from devharness.core.config import list_config_keys

    keys = list_config_keys()
    click.echo("Configurable settings:\n")
    for k in keys:
        type_label = f"[{k['type']}]"
        click.echo(f"  {k['key']:35s} {type_label:10s} {k['description']}")


@config.command("get")
@click.argument("key")
@click.pass_context
def config_get(ctx: click.Context, key: str) -> None:
    """Get a config setting value."""
    import anyio

    cfg = ctx.obj["config"]

    async def _get() -> None:
        from devharness.core.config import CREDENTIAL_KEYS, SETTINGS_KEYS
        from devharness.storage.sqlite import SqliteStorage

        storage = SqliteStorage(cfg.get_db_path())
        await storage.initialize()

        if key in SETTINGS_KEYS:
            value = await storage.get_setting(key)
            if value is None:
                field = SETTINGS_KEYS[key]["field"]
                value = str(getattr(cfg, field))
                click.echo(f"{key} = {value} (default)")
            else:
                click.echo(f"{key} = {value}")
        elif key in CREDENTIAL_KEYS:
            meta = CREDENTIAL_KEYS[key]
            value = await storage.load_credential(None, meta["provider"], meta["key_name"])
            if value:
                # Mask credential value
                click.echo(f"{key} = {value[:4]}...{value[-4:]}" if len(value) > 8 else f"{key} = ****")
            else:
                click.echo(f"{key} = (not set)")
        else:
            click.echo(f"Unknown key: {key}", err=True)

        await storage.close()

    anyio.run(_get)


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set(ctx: click.Context, key: str, value: str) -> None:
    """Set a config setting value."""
    import anyio

    cfg = ctx.obj["config"]

    async def _set() -> None:
        from devharness.core.config import save_config_to_db
        from devharness.storage.sqlite import SqliteStorage

        storage = SqliteStorage(cfg.get_db_path())
        await storage.initialize()

        try:
            await save_config_to_db(key, value, storage)
            click.echo(f"{key} = {value}")
        except ValueError as e:
            click.echo(str(e), err=True)

        await storage.close()

    anyio.run(_set)


@config.command("set-credential")
@click.argument("key")
@click.argument("value")
@click.pass_context
def config_set_credential(ctx: click.Context, key: str, value: str) -> None:
    """Set a credential (API key, password, token)."""
    import anyio

    cfg = ctx.obj["config"]

    async def _set() -> None:
        from devharness.core.config import CREDENTIAL_KEYS, save_config_to_db
        from devharness.storage.sqlite import SqliteStorage

        storage = SqliteStorage(cfg.get_db_path())
        await storage.initialize()

        if key not in CREDENTIAL_KEYS:
            click.echo(
                f"Unknown credential: {key}\n"
                f"Valid: {', '.join(sorted(CREDENTIAL_KEYS.keys()))}",
                err=True,
            )
        else:
            await save_config_to_db(key, value, storage)
            click.echo(f"Credential {key} saved")

        await storage.close()

    anyio.run(_set)


if __name__ == "__main__":
    cli()
