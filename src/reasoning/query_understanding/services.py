from langchain_core.language_models import BaseChatModel

from reasoning.core_models import VerificationIssue

from .models import QueryUnderstanding


class QueryUnderstandingService:
    def __init__(
        self,
        llm: BaseChatModel,
    ):
        self.llm = llm

    async def understand(
        self,
        question: str,
        feedback: tuple[VerificationIssue, ...] = (),
    ) -> QueryUnderstanding:

        del feedback

        # TODO:

        raise NotImplementedError
