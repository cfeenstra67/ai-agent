import logging
from datetime import datetime
from typing import Optional, List

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ai_agent.agent import Agent, AgentMessage, Context
from ai_agent.api import AgentWrapper, message_provider
from ai_agent.modular_agent import MessageProvider, AgentMessage


LOGGER = logging.getLogger(__name__)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class AgentHistoryItem(Base):
    __tablename__ = "agent_history_item"

    item_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int]
    agent: Mapped[str]
    event_id: Mapped[Optional[int]]
    index: Mapped[int]
    actor: Mapped[str]
    message: Mapped[str]
    is_result: Mapped[bool]
    created_at: Mapped[datetime]


class AgentHistoryService(MessageProvider):
    """
    """
    def __init__(self, num_history_messages: int = 5) -> None:
        self.num_history_messages = num_history_messages

    def get_sqlalchemy_metadata(self) -> sa.MetaData:
        return Base.metadata

    async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
        history = await ctx.get_event_history(
            type="agent",
            destination=agent,
            limit=self.num_history_messages,
        )
        out = []
        for item in history:
            out.append(AgentMessage(item.payload["message"]))
            if item.result is not None:
                out.append(AgentMessage(item.result, "assistant"))

        return out[-self.num_history_messages:]

    def __call__(self, agent: Agent, ctx: Context) -> Agent:

        async def chat(messages: List[AgentMessage], ctx: Context):
            result = await agent.chat(messages, ctx)
            now = datetime.utcnow()
            async with ctx.session_ctx() as session:
                idx = 0
                for msg in messages:
                    session.add(AgentHistoryItem(
                        session_id=ctx.session_id,
                        agent=agent.name,
                        event_id=ctx.event_id,
                        index=idx,
                        actor=msg.actor,
                        message=msg.message,
                        is_result=False,
                        created_at=now,
                    ))
                    idx += 1
                
                session.add(AgentHistoryItem(
                    session_id=ctx.session_id,
                    agent=agent.name,
                    event_id=ctx.event_id,
                    index=idx,
                    actor="assistant",
                    message=result,
                    is_result=True,
                    created_at=now,
                ))
                await session.commit()

            return result

        return AgentWrapper(agent, new_chat=chat)
