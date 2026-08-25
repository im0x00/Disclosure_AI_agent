from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel


@dataclass(frozen=True)
class LLMRegistry:
    reasoning: BaseChatModel
    generation: BaseChatModel


def build_llms() -> LLMRegistry:
    raise NotImplementedError("LLM initialization is not implemented yet")
