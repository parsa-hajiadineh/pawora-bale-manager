from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from sqlalchemy.orm import Session

from bale_inviter.adapters.bale import BaleConfigError
from bale_inviter.adapters.factory import create_bale_adapter
from bale_inviter.adapters.telegram import login_telegram_session
from bale_inviter.config import get_settings
from bale_inviter.database.session import create_db_engine, create_session_factory, init_db
from bale_inviter.importers.service import ImportService
from bale_inviter.logging_setup import setup_logging
from bale_inviter.queue.service import QueueService
from bale_inviter.queue.worker import build_worker
from bale_inviter.reporting.service import ReportingService
from bale_inviter.services.account_check import AccountCheckService
from bale_inviter.services.bot_runtime import BotRuntime
from bale_inviter.services.invite import InviteService

app = typer.Typer(help="Invite Excel contacts to a Telegram group by phone (user session, not a bot).")


@contextmanager
def session_scope() -> Iterator[Session]:
    settings = get_settings()
    engine = init_db(create_db_engine(settings.database_url), settings)
    factory = create_session_factory(engine)
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@app.callback()
def _init() -> None:
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_dir)


def _adapter_or_exit():
    settings = get_settings()
    try:
        return settings, create_bale_adapter(settings)
    except BaleConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc


@app.command("init-db")
def init_database() -> None:
    """Create SQLite tables."""
    settings = get_settings()
    init_db(create_db_engine(settings.database_url), settings)
    typer.echo(f"Database ready at {settings.database_url}")


@app.command("import-contacts")
def import_contacts(
    file_path: Path = typer.Argument(..., exists=True, readable=True, help="Excel or CSV file"),
) -> None:
    """Import contacts from Excel/CSV. Repeatable; duplicates are skipped/updated."""
    with session_scope() as session:
        result = ImportService(session).import_file(file_path)
    typer.echo(
        "\n".join(
            [
                f"file: {result.source_filename}",
                f"total: {result.total}",
                f"valid: {result.valid}",
                f"invalid: {result.invalid}",
                f"duplicate: {result.duplicate}",
                f"created: {result.created}",
                f"updated: {result.updated}",
            ]
        )
    )


@app.command("report")
def report() -> None:
    """Print contact status summary."""
    with session_scope() as session:
        summary = ReportingService(session).as_dict()
    typer.echo("Contact summary")
    for key, value in summary.items():
        typer.echo(f"  {key}: {value}")


@app.command("telegram-login")
def telegram_login() -> None:
    """Log in once with your Telegram account. Run this in PowerShell, not inside chat."""
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        typer.secho(
            "Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env (free: https://my.telegram.org)",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)
    phone = (settings.telegram_phone or "").strip() or typer.prompt("Your Telegram phone (example +98912...)")
    typer.echo("Telegram will send a login code to the app.")

    def _code() -> str:
        return typer.prompt("Login code")

    def _password() -> str:
        return typer.prompt("Two-step password", hide_input=True)

    try:
        info = asyncio.run(
            login_telegram_session(
                settings.telegram_api_id,
                settings.telegram_api_hash,
                settings.telegram_session_path,
                phone,
                _code,
                _password,
            )
        )
    except Exception as exc:  # noqa: BLE001
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(f"logged in id={info.id} username={info.username or '-'}")


@app.command("ping-bale")
def ping_bale() -> None:
    """Verify the configured messenger session (Telegram user or Bale bot)."""
    settings, adapter = _adapter_or_exit()
    info = asyncio.run(adapter.verify_credentials())
    platform = settings.messenger_platform or settings.bale_adapter
    typer.echo(
        f"ok platform={platform} id={info.id} username={info.username or '-'} is_bot={info.is_bot}"
    )
    if not settings.group_id:
        typer.echo("GROUP_ID is empty. Put the Telegram group id or @username in .env")


@app.command("run-invites")
def run_invites() -> None:
    """Check phones on Telegram, then invite those with an account. Not one-by-one manual sends."""
    settings, adapter = _adapter_or_exit()
    with session_scope() as session:
        checks = AccountCheckService(session, adapter, QueueService(session, settings)).enqueue_pending()
    typer.echo(f"queued account checks: {checks.queued}")
    _drain_jobs(adapter, settings)
    with session_scope() as session:
        invites = InviteService(session, adapter, QueueService(session, settings), settings).enqueue_pending()
    typer.echo(f"queued direct invites: {invites.queued_direct}")
    _drain_jobs(adapter, settings)
    typer.echo("invite run finished. Use: python -m bale_inviter report")


def _drain_jobs(adapter, settings) -> None:
    while True:
        with session_scope() as session:
            job_worker = build_worker(session, adapter, settings, interval_seconds=0)
            processed = asyncio.run(job_worker.process_one())
        if not processed:
            return
        typer.echo("processed 1 job")
        time.sleep(max(0, settings.invite_interval))


@app.command("prepare-group")
def prepare_group() -> None:
    """Export the group invite link. Bot must be a group admin with invite permission."""
    settings, adapter = _adapter_or_exit()
    if not settings.group_id and not settings.invite_link:
        typer.secho("Set GROUP_ID or INVITE_LINK in .env first.", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    info = asyncio.run(adapter.verify_credentials())
    with session_scope() as session:
        link = asyncio.run(InviteService(session, adapter, settings=settings).ensure_invite_link())
    typer.echo(f"bot=@{info.username or '-'} invite_link={link}")


@app.command("enqueue-account-checks")
def enqueue_account_checks(
    include_errors: bool = typer.Option(False, help="Also re-queue contacts in ERROR status"),
) -> None:
    """Queue CHECK_BALE_ACCOUNT jobs for valid contacts that are still UNKNOWN."""
    settings, adapter = _adapter_or_exit()
    with session_scope() as session:
        queue = QueueService(session, settings)
        result = AccountCheckService(session, adapter, queue).enqueue_pending(include_errors=include_errors)
    typer.echo(
        "\n".join(
            [
                f"eligible: {result.eligible}",
                f"queued: {result.queued}",
                f"skipped_duplicate: {result.skipped_duplicate}",
                f"without_user_id: {result.skipped_no_user_id}",
            ]
        )
    )


@app.command("enqueue-invites")
def enqueue_invites(
    strategy: str = typer.Option("auto", help="auto (direct then link fallback), direct, or link"),
) -> None:
    """Queue DIRECT_INVITE and/or SEND_INVITE_LINK jobs for contacts that have bale_user_id."""
    settings, adapter = _adapter_or_exit()
    with session_scope() as session:
        queue = QueueService(session, settings)
        result = InviteService(session, adapter, queue, settings).enqueue_pending(strategy=strategy)
    typer.echo(
        "\n".join(
            [
                f"queued_direct: {result.queued_direct}",
                f"queued_link: {result.queued_link}",
                f"skipped_duplicate: {result.skipped_duplicate}",
                f"eligible_direct: {result.eligible_direct}",
                f"eligible_link: {result.eligible_link}",
            ]
        )
    )
    typer.echo("Contacts without a Telegram account are skipped.")
    typer.echo("Run enqueue-account-checks first, or use run-invites.")


@app.command("worker")
def worker(
    once: bool = typer.Option(False, help="Process at most one due job and exit"),
) -> None:
    """Run queued CHECK / DIRECT_INVITE / SEND_INVITE_LINK / CHECK_JOIN_STATUS jobs."""
    settings, adapter = _adapter_or_exit()
    processed_any = False
    while True:
        with session_scope() as session:
            job_worker = build_worker(session, adapter, settings, interval_seconds=0)
            processed = asyncio.run(job_worker.process_one())
        if processed:
            processed_any = True
            typer.echo("processed 1 job")
            if once:
                return
            time.sleep(max(0, settings.invite_interval))
            continue
        if once:
            typer.echo("idle" if not processed_any else "done")
            return
        time.sleep(max(1, settings.worker_poll_seconds))


@app.command("run-bot")
def run_bot() -> None:
    """Self-manage: answer /start, match shared contacts, invite, and drain the job queue."""
    settings, adapter = _adapter_or_exit()
    typer.echo("runtime started; Ctrl+C to stop")
    typer.echo("Ask colleagues to open the bot and tap Start, or send their contact.")
    while True:
        with session_scope() as session:
            runtime = BotRuntime(session, adapter, settings)
            inbound = asyncio.run(runtime.process_inbound(timeout=0))
            job_worker = build_worker(session, adapter, settings, interval_seconds=0)
            processed = asyncio.run(job_worker.process_one())
        if inbound or processed:
            if inbound:
                typer.echo(f"handled {inbound} update(s)")
            if processed:
                typer.echo("processed 1 job")
            time.sleep(max(0, settings.invite_interval))
            continue
        time.sleep(max(1, settings.worker_poll_seconds))


@app.command("sync-bot-updates")
def sync_bot_updates() -> None:
    """Read inbound getUpdates once and match shared contacts."""
    settings, adapter = _adapter_or_exit()
    with session_scope() as session:
        runtime = BotRuntime(session, adapter, settings)
        inbound = asyncio.run(runtime.process_inbound(timeout=0))
    typer.echo(f"handled={inbound}")


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the local report API."""
    import uvicorn

    uvicorn.run("bale_inviter.main:app", host=host, port=port, reload=False)
