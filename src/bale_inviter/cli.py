from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import typer
from sqlalchemy.orm import Session

from bale_inviter.config import get_settings
from bale_inviter.database.session import create_db_engine, create_session_factory, init_db
from bale_inviter.importers.service import ImportService
from bale_inviter.logging_setup import setup_logging
from bale_inviter.reporting.service import ReportingService

app = typer.Typer(help="Bale contact manager — phase 1 (no invites, no private messages).")


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


@app.command("serve")
def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the local report API. Does not talk to Bale."""
    import uvicorn

    uvicorn.run("bale_inviter.main:app", host=host, port=port, reload=False)
