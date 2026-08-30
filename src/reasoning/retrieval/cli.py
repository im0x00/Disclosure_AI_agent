"""Operator commands for building the retrieval embedding index."""

from __future__ import annotations

import argparse
import asyncio
import importlib
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from psycopg_pool import AsyncConnectionPool

from .config import RetrievalRuntimeConfig
from .index_scope import load_mini_world, resolve_mini_world
from .indexer import DocumentGrainEmbeddingIndexer, EmbeddingIndexProgress
from .model_providers import SentenceTransformerEmbeddingProvider
from .retrieval import EmbeddingProvider
from .schema_loader import SchemaLoader


def _load_factory(path: str) -> Callable[[], object]:
    module_name, separator, attribute_name = path.partition(":")
    if not separator or not module_name or not attribute_name:
        raise ValueError("provider factory must have the form package.module:function")
    module = importlib.import_module(module_name)
    factory = getattr(module, attribute_name)
    if not callable(factory):
        raise TypeError("provider factory is not callable")
    return cast(Callable[[], object], factory)


async def _resolve_provider(factory_path: str | None) -> EmbeddingProvider:
    if factory_path is None:
        return await asyncio.to_thread(
            SentenceTransformerEmbeddingProvider,
            RetrievalRuntimeConfig.from_environment().models,
        )
    value = _load_factory(factory_path)()
    if inspect.isawaitable(value):
        value = await value
    provider = cast(EmbeddingProvider, value)
    if not provider.model_id or provider.dimensions <= 0:
        raise ValueError("provider must expose model_id and positive dimensions")
    return provider


async def _index(args: argparse.Namespace) -> None:
    runtime_config = RetrievalRuntimeConfig.from_environment()
    print("stage=load-model", flush=True)
    provider = await _resolve_provider(args.provider_factory)
    provider_device = getattr(provider, "device", "provider-defined")
    print(
        f"stage=model-ready model_id={provider.model_id} "
        f"dimensions={provider.dimensions} device={provider_device}",
        flush=True,
    )
    document_ids: tuple[str, ...] | None = None
    scope_message = "scope=full"
    if args.mini_world is not None:
        print("stage=resolve-mini-world", flush=True)
        resolution = resolve_mini_world(
            load_mini_world(args.mini_world),
            profile_path=args.mini_world,
            manifest_path=args.manifest,
            relations_path=args.relations,
        )
        document_ids = resolution.document_ids
        scope_message = (
            f"scope={resolution.world_id} documents={len(document_ids)} "
            f"base_documents={resolution.base_document_count} "
            f"closure_documents={resolution.closure_document_count}"
        )
    print(f"stage=index {scope_message}", flush=True)
    async with AsyncConnectionPool[Any](
        conninfo=str(args.database_url),
        min_size=1,
        max_size=2,
        open=False,
    ) as pool:
        indexer = DocumentGrainEmbeddingIndexer(
            pool=pool,
            embedding_provider=provider,
            batch_size=args.batch_size or runtime_config.models.embedding_batch_size,
            scheduling_window_batches=(
                args.scheduling_window_batches
                or runtime_config.models.embedding_scheduling_window_batches
            ),
        )
        progress = _progress_reporter(
            max_embedding_hours=args.max_embedding_hours,
            throughput_gate_grains=args.throughput_gate_grains,
        )
        report = await indexer.index_pending(
            max_grains=args.max_grains,
            document_ids=document_ids,
            progress=progress,
            progress_every_windows=args.progress_every_windows,
        )
        print("stage=build-vector-index", flush=True)
        async with pool.connection() as connection:
            await connection.execute(
                "SELECT corpus.create_document_grain_embedding_index(%s, %s, %s)",
                (
                    report.model_id,
                    report.dimensions,
                    runtime_config.query.vector_metric.value,
                ),
            )
            await connection.commit()
        print("stage=vector-index-ready", flush=True)
    print(
        f"indexed={report.indexed} model_id={report.model_id} "
        f"dimensions={report.dimensions} {scope_message}"
    )


def _print_progress(progress: EmbeddingIndexProgress) -> None:
    eta = "unknown" if progress.eta_seconds is None else _duration(progress.eta_seconds)
    print(
        f"stage=index-progress indexed={progress.indexed}/{progress.total} "
        f"rate={progress.grains_per_second:.2f}_grains_per_second eta={eta}",
        flush=True,
    )


def _progress_reporter(
    *,
    max_embedding_hours: float | None,
    throughput_gate_grains: int,
) -> Callable[[EmbeddingIndexProgress], None]:
    if max_embedding_hours is not None and max_embedding_hours <= 0:
        raise ValueError("max_embedding_hours must be positive")
    if throughput_gate_grains < 1:
        raise ValueError("throughput_gate_grains must be positive")

    def report(progress: EmbeddingIndexProgress) -> None:
        _print_progress(progress)
        if (
            max_embedding_hours is None
            or progress.indexed < throughput_gate_grains
            or progress.eta_seconds is None
        ):
            return
        projected_seconds = progress.elapsed_seconds + progress.eta_seconds
        allowed_seconds = max_embedding_hours * 3600
        if projected_seconds > allowed_seconds:
            raise RuntimeError(
                "projected embedding time exceeds the configured limit: "
                f"projected={_duration(projected_seconds)} "
                f"limit={_duration(allowed_seconds)}; committed rows are reusable, "
                "restart the same scope on a faster device"
            )

    return report


def _duration(seconds: float) -> str:
    total_seconds = max(0, int(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, remaining_seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"


def _preview_mini_world(args: argparse.Namespace) -> None:
    resolution = resolve_mini_world(
        load_mini_world(args.mini_world),
        profile_path=args.mini_world,
        manifest_path=args.manifest,
        relations_path=args.relations,
    )
    print(resolution.model_dump_json())


async def _install_schema(args: argparse.Namespace) -> None:
    report = await SchemaLoader(database_url=str(args.database_url)).install()
    print("installed=" + ",".join(report.installed_scripts))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m reasoning.retrieval.cli")
    subparsers = parser.add_subparsers(dest="command", required=True)

    install_schema = subparsers.add_parser("install-schema")
    install_schema.add_argument("--database-url", required=True)

    index = subparsers.add_parser("index")
    index.add_argument("--database-url", required=True)
    index.add_argument("--provider-factory")
    index.add_argument("--batch-size", type=int)
    index.add_argument("--scheduling-window-batches", type=int)
    index.add_argument("--max-grains", type=int)
    index.add_argument(
        "--progress-every-windows",
        "--progress-every-batches",
        dest="progress_every_windows",
        type=int,
        default=1,
    )
    index.add_argument("--max-embedding-hours", type=float)
    index.add_argument("--throughput-gate-grains", type=int, default=2048)
    index.add_argument("--mini-world", type=Path)
    index.add_argument("--manifest", type=Path, default=Path("corpus/manifest.jsonl"))
    index.add_argument(
        "--relations",
        type=Path,
        default=Path("outputs/relations/relations.jsonl"),
    )

    preview = subparsers.add_parser("preview-mini-world")
    preview.add_argument("--mini-world", type=Path, required=True)
    preview.add_argument("--manifest", type=Path, default=Path("corpus/manifest.jsonl"))
    preview.add_argument(
        "--relations",
        type=Path,
        default=Path("outputs/relations/relations.jsonl"),
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "install-schema":
        asyncio.run(_install_schema(args))
    elif args.command == "index":
        asyncio.run(_index(args))
    elif args.command == "preview-mini-world":
        _preview_mini_world(args)


if __name__ == "__main__":
    main()
