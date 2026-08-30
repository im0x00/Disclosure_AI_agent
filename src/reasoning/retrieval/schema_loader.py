"""Install retrieval-owned PostgreSQL schema separately from runtime startup."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from psycopg import AsyncConnection


@dataclass(frozen=True, slots=True)
class SchemaInstallReport:
    installed_scripts: tuple[str, ...]


class SchemaLoader:
    """Load only retrieval DDL; embedding data remains an indexing concern."""

    _LOCK_NAME = "reasoning.retrieval.install-schema"
    _SCHEMA_SCRIPTS = ("013_create_retrieval_indexes.sql",)

    def __init__(
        self,
        *,
        database_url: str,
        sql_directory: Path | None = None,
    ) -> None:
        if not database_url:
            raise ValueError("database_url must not be empty")
        self._database_url = database_url
        self._sql_directory = sql_directory or Path(__file__).resolve().parents[2] / "sql"

    async def install(self) -> SchemaInstallReport:
        scripts = tuple(self._load_script(name) for name in self._SCHEMA_SCRIPTS)
        installed: list[str] = []

        async with await AsyncConnection.connect(
            self._database_url,
            autocommit=True,
        ) as connection:
            await connection.execute(
                "SELECT pg_advisory_lock(hashtext(%s))",
                (self._LOCK_NAME,),
            )
            try:
                for name, script in zip(self._SCHEMA_SCRIPTS, scripts, strict=True):
                    # No parameters are passed: psycopg uses PostgreSQL's simple
                    # query path, which preserves the SQL file's own transaction.
                    await connection.execute(script)
                    installed.append(name)
            finally:
                await connection.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))",
                    (self._LOCK_NAME,),
                )

        return SchemaInstallReport(installed_scripts=tuple(installed))

    def _load_script(self, name: str) -> str:
        path = self._sql_directory / name
        if not path.is_file():
            raise FileNotFoundError(f"retrieval schema script not found: {path}")
        script = path.read_text(encoding="utf-8").strip()
        if not script:
            raise ValueError(f"retrieval schema script is empty: {path}")
        return script
