import abc
import dataclasses as dc
from typing import List

from ai_agent.context import Context


@dc.dataclass(frozen=True)
class Message:
    """
    """
    content: str
    actor: str


@dc.dataclass(frozen=True)
class Prompt:
    """
    """
    messages: List[Message]


class Agent(abc.ABC):
    """
    """
    name: str

    description: str

    @abc.abstractmethod
    def get_prompt(self, context: Context) -> Prompt:
        """
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def chat(self, messages: List[Message]) -> str:
        """
        """
        raise NotImplementedError
