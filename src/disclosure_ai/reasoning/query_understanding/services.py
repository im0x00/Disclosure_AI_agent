from langchain_core.language_models import BaseChatModel

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
    ) -> QueryUnderstanding:

        # TODO:
        # prompt = markdown prompt loader로 생성
        #
        # result = await self.llm
        #     .with_structured_output(
        #         QueryUnderstanding
        #     )
        #     .ainvoke(...)

        raise NotImplementedError
