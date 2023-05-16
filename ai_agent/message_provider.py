import abc

from ai_agent.command import Context


class MessageProvider(abc.ABC):
    """
    """
    @abc.abstractmethod
    async def get_messages(self, service: str, ctx: Context) -> None:
        """
        """
        raise NotImplementedError
