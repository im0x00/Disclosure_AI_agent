"""Application service joining query compilation to one batched backend call."""

from __future__ import annotations

from .errors import RetrievalDataError
from .models import RetrievalFrame, SearchBatchResult
from .retrieval import RetrievalQueryCompiler, RetrievalSearchBackend


class RetrievalBatchService:
    def __init__(
        self,
        *,
        query_compiler: RetrievalQueryCompiler,
        search_backend: RetrievalSearchBackend,
    ) -> None:
        self._query_compiler = query_compiler
        self._search_backend = search_backend

    async def search(self, frame: RetrievalFrame) -> tuple[SearchBatchResult, ...]:
        requests = self._query_compiler.compile(frame)
        results = await self._search_backend.search_many(requests)
        if len(results) != len(requests):
            raise RetrievalDataError("retrieval backend returned an invalid result count")
        for request, result in zip(requests, results, strict=True):
            if result.request.target_id != request.target_id:
                raise RetrievalDataError("retrieval backend changed request ordering")
        return results
