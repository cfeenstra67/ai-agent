import argparse
import logging
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ai_agent.agent import Command
from ai_agent.argparse_command import argparse_command


LOGGER = logging.getLogger(__name__)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class ChatRoomMessage(Base):
    """
    """
    __tablename__ = "chat_room_message"

    message_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int]
    source_type: Mapped[str]
    source_destination: Mapped[str]
    message: Mapped[str]
    created_at: Mapped[datetime]


class ChatRoomService:
    """
    """
    def get_sqlalchemy_metadata(self) -> sa.MetaData:
        return Base.metadata

    def chat_command(self, name: str = "chat") -> Command:
        parser = argparse.ArgumentParser(
            prog=name,
            description=(
                "Add a message to a shared chat room. The message "
                "may either be arguments or the body of the command"
            ),
            add_help=False
        )
        parser.add_argument(
            "message",
            nargs="+",
            help="The message to send to the chat room"
        )

        @argparse_command(parser=parser)
        async def chat(ns, body, ctx):
            async with ctx.session_ctx() as session:
                if not ctx.event.source_type:
                    LOGGER.warn("Ignoring anonymous chat command")
                    return

                msg = body
                if msg is None:
                    msg = " ".join(ns.message)
                message = ChatRoomMessage(
                    session_id=ctx.session_id,
                    source_type=ctx.event.source_type,
                    source_destination=ctx.event.source_destination,
                    message=msg,
                    created_at=datetime.utcnow()
                )
                session.add(message)
                await session.commit()

                agent_message = (
                    f"New chat message:\n"
                    f"{ctx.event.source_destination}: {msg}"
                )
                sent = 0

                for agent in ctx.get_agents():
                    if ctx.event.source_type == "agent" and agent == ctx.event.source_destination:
                        continue
                    await ctx.queue_agent(agent, agent_message)
                    sent += 1
                
                LOGGER.debug("Sent chat to %d agent(s)", sent)

        return chat
