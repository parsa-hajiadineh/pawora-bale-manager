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
from bale_inviter.config import get_settings
from bale_inviter.database.session import create_db_engine, create_session_factory, init_db
from bale_inviter.importers.service import ImportService
from bale_inviter.logging_setup import setup_logging
from bale_inviter.queue.service import QueueService
from bale_inviter.queue.worker import build_account_check_worker
from bale_inviter.reporting.service import ReportingService
from bale_inviter.services.account_check import AccountCheckService

app = typer.Typer(help="Bale contact manager — phase 2 (account checks only; no invites or private messages).")


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


@app.command("ping-bale")
def ping_bale() -> None:
    """Verify BALE_BOT_TOKEN with getMe. Does not send messages."""
    settings = get_settings()
    try:
        adapter = create_bale_adapter(settings)
        info = asyncio.run(adapter.verify_credentials())
    except BaleConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    typer.echo(f"bot ok id={info.id} username={info.username or '-'} is_bot={info.is_bot}")


@app.command("enqueue-account-checks")
def enqueue_account_checks(
    include_errors: bool = typer.Option(False, help="Also re-queue contacts in ERROR status"),
) -> None:
    """Queue CHECK_BALE_ACCOUNT jobs for valid contacts that are still UNKNOWN."""
    settings = get_settings()
    try:
        adapter = create_bale_adapter(settings)
    except BaleConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
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
    typer.echo(
        "Note: official Bale Bot API cannot look up accounts by phone. "
        "Checks succeed only when bale_user_id is already known."
    )


@app.command("worker")
def worker(
    once: bool = typer.Option(False, help="Process at most one due job and exit"),
) -> None:
    """Run CHECK_BALE_ACCOUNT jobs. Does not invite or send private messages."""
    settings = get_settings()
    try:
        adapter = create_bale_adapter(settings)
    except BaleConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    processed_any = False
    while True:
        with session_scope() as session:
            job_worker = build_account_check_worker(
                session, adapter, settings, interval_seconds=0
            )
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


@app.command("sync-bot-updates")
def sync_bot_updates() -> None:
    """Read inbound getUpdates and match shared contacts. Does not send messages."""
    settings = get_settings()
    try:
        adapter = create_bale_adapter(settings)
    except BaleConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc
    with session_scope() as session:
        result = asyncio.run(AccountCheckService(session, adapter).sync_shared_contacts())
    typer.echo(
        f"scanned={result.scanned} matched={result.matched} unmatched={result.unmatched}"
    )


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the local report API."""
    import uvicorn

    uvicorn.run("bale_inviter.main:app", host=host, port=port, reload=False)
