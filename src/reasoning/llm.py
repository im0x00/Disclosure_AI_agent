from dataclasses import dataclass
from typing import cast

from langchain_core.language_models import BaseChatModel
from langchain_naver import ChatClovaX


@dataclass(frozen=True)
class LLMRegistry:
    default: BaseChatModel
    reasoning: BaseChatModel
    generation: BaseChatModel


@dataclass(frozen=True)
class ClovaModelSettings:
    model: str = "HCX-007"
    timeout_seconds: float = 60.0
    default_max_tokens: int = 2048
    reasoning_max_tokens: int = 4096
    generation_max_tokens: int = 2048


def build_llms(settings: ClovaModelSettings | None = None) -> LLMRegistry:
    resolved = settings or ClovaModelSettings()
    return LLMRegistry(
        default=_build_clova_model(
            resolved,
            max_tokens=resolved.default_max_tokens,
        ),
        reasoning=_build_clova_model(
            resolved,
            max_tokens=resolved.reasoning_max_tokens,
        ),
        generation=_build_clova_model(
            resolved,
            max_tokens=resolved.generation_max_tokens,
        ),
    )


def _build_clova_model(
    settings: ClovaModelSettings,
    *,
    max_tokens: int,
) -> BaseChatModel:
    model = ChatClovaX(
        model=settings.model,
        temperature=0.0,
        max_completion_tokens=max_tokens,
        reasoning_effort="none",
        timeout=settings.timeout_seconds,
        max_retries=0,
    )
    return cast(BaseChatModel, model)


async def close_llms(registry: LLMRegistry) -> None:
    closed: set[int] = set()
    for model in (registry.default, registry.reasoning, registry.generation):
        if id(model) in closed or not isinstance(model, ChatClovaX):
            continue
        closed.add(id(model))
        if model.root_async_client is not None:
            await model.root_async_client.close()
        if model.root_client is not None:
            model.root_client.close()
