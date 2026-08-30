"""Retrieval failures classified by whether repeating the same call can help."""

from __future__ import annotations


class RetrievalError(Exception):
    retryable: bool = False


class RetrievalTemporaryError(RetrievalError):
    retryable = True


class RetrievalConfigurationError(RetrievalError):
    pass


class RetrievalDataError(RetrievalError):
    pass
