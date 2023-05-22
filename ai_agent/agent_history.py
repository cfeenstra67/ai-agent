import copy
import logging
from datetime import datetime
from functools import wraps
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ai_agent.agent import Agent, Context
from ai_agent.modular_agent import ModularAgent, MessageProvider, MessageFactory, AgentMessage


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


class AgentHistoryService:
    """
    """
    def get_sqlalchemy_metadata(self) -> sa.MetaData:
        return Base.metadata

    def message_provider(
        self,
        agent: str,
        num_messages: int = 5,
    ) -> MessageProvider:
        
        class HistoryMessageProvider(MessageProvider):

            async def get_messages(self, ctx: Context):
                history = await ctx.get_event_history(
                    type="agent",
                    destination=agent,
                    limit=num_messages,
                )
                out = []
                for item in history:
                    out.append(AgentMessage(item.payload["message"]))
                    if item.result is not None:
                        out.append(AgentMessage(item.result, "assistant"))

                return out[-num_messages:]

        return HistoryMessageProvider()

    def middleware(self, agent: Agent, ctx: Context) -> Agent:
        if not isinstance(agent, ModularAgent):
            LOGGER.warn("History only implemented for ModularAgents")
            return agent

        agent_copy = copy.copy(agent)

        @wraps(agent_copy.chat)
        async def chat(message: str, ctx: Context):
            messages = await agent.get_messages(message, ctx)
            result = await agent.chatter.chat(messages)
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

        agent_copy.chat = chat

        return agent_copy
