import httpx
import openai
import psycopg

from reasoning.retrieval.errors import RetrievalError


def is_transient_error(error: Exception) -> bool:
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, RetrievalError):
            return current.retryable
        if isinstance(
            current,
            (
                TimeoutError,
                ConnectionError,
                httpx.TimeoutException,
                httpx.NetworkError,
                openai.APITimeoutError,
                openai.APIConnectionError,
                openai.RateLimitError,
                openai.InternalServerError,
                psycopg.OperationalError,
            ),
        ):
            return True
        if isinstance(current, httpx.HTTPStatusError):
            status = current.response.status_code
            if status in {408, 409, 425, 429} or status >= 500:
                return True
        if isinstance(current, openai.APIStatusError):
            if current.status_code in {408, 409, 425, 429} or current.status_code >= 500:
                return True
        current = current.__cause__ or current.__context__
    return False
