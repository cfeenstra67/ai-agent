import argparse
from datetime import datetime
from typing import Optional, List

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ai_agent.agent import AgentMessage, Command, Context
from ai_agent.api import message_provider
from ai_agent.argparse_command import argparse_command
from ai_agent.modular_agent import MessageProvider, AgentMessage


class Base(AsyncAttrs, DeclarativeBase):
    pass


class WorkingMemoryItem(Base):
    __tablename__ = "working_memory_item"

    item_id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int]
    agent: Mapped[str]
    value: Mapped[str]
    created_at: Mapped[datetime]
    created_by_event_id: Mapped[Optional[int]]
    updated_at: Mapped[datetime]
    updated_by_event_id: Mapped[Optional[int]]
    deleted_at: Mapped[Optional[datetime]]
    deleted_by_event_id: Mapped[Optional[int]]


def working_memory_add_parser(name: str):
    parser = argparse.ArgumentParser(
        prog=name,
        description="Add an item to working memory",
        add_help=False,
    )
    parser.add_argument(
        "item",
        help="A string that will be added to working memory",
        nargs="+"
    )
    return parser


def working_memory_rm_parser(name: str):
    parser = argparse.ArgumentParser(
        prog=name,
        description="Remove an item from working memory",
        add_help=False,
    )
    parser.add_argument(
        "item_id",
        help="ID of the item you'd like to delete",
        type=int,
        nargs="+"
    )
    return parser


def working_memory_replace_parser(name: str):
    parser = argparse.ArgumentParser(
        prog=name,
        description="Replace an existing item with a new one",
        add_help=False
    )
    parser.add_argument(
        "item_id",
        help="ID of the item you'd like to remove",
        type=int,
    )
    parser.add_argument(
        "item",
        help="A string you'd like to add in its place"
    )
    return parser


class WorkingMemoryService(MessageProvider):
    """
    """
    def __init__(self, prefix: str = "workmem-", command_priority: int = 9) -> None:
        self.prefix = prefix
        self.command_priority = command_priority
    
    def get_sqlalchemy_metadata(self) -> sa.MetaData:
        return Base.metadata

    async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
        async with ctx.session_ctx() as session:
            result = await session.execute(
                sa.select(WorkingMemoryItem)
                .where(WorkingMemoryItem.deleted_at == None)
                .where(WorkingMemoryItem.session_id == ctx.session_id)
                .where(WorkingMemoryItem.agent == agent)
            )

            lines = ["Working memory items:"]
            for item in result.scalars():
                lines.append(f"{item.item_id}: {item.value}")
            
            if len(lines) == 1:
                lines.append("Items will appear here when you add them")

            return [AgentMessage("\n\n".join(lines))]

    def commands(self) -> List[Command]:

        def get_agent(ctx):
            if ctx.event.source_type != "agent":
                raise ValueError(f"Working memory is only available to agents")
            return ctx.event.source_destination

        @argparse_command(
            parser=working_memory_add_parser(self.prefix + "add"),
            priority=self.command_priority,
        )
        async def working_memory_add(ns, body, ctx):
            now = datetime.utcnow()
            agent = get_agent(ctx)
            async with ctx.session_ctx() as session:
                item = WorkingMemoryItem(
                    session_id=ctx.session_id,
                    agent=agent,
                    value=" ".join(ns.item),
                    created_at=now,
                    created_by_event_id=ctx.event_id,
                    updated_at=now,
                    updated_by_event_id=ctx.event_id,
                )
                session.add(item)
                await session.commit()
                return None
    
        @argparse_command(
            parser=working_memory_rm_parser(self.prefix + "rm"),
            priority=self.command_priority,
        )
        async def working_memory_rm(ns, body, ctx):
            now = datetime.utcnow()
            agent = get_agent(ctx)
            async with ctx.session_ctx() as session:
                result = await session.execute(
                    sa.select(WorkingMemoryItem)
                    .where(WorkingMemoryItem.deleted_at == None)
                    .where(WorkingMemoryItem.session_id == ctx.session_id)
                    .where(WorkingMemoryItem.agent == agent)
                    .where(WorkingMemoryItem.item_id.in_(ns.item_id))
                )
                for item in result.scalars():
                    item.deleted_at = now
                    item.deleted_by_event_id = ctx.event_id
                    session.add(item)
                
                await session.commit()
                return None

        @argparse_command(
            parser=working_memory_replace_parser(self.prefix + "replace"),
            priority=self.command_priority,
        )
        async def working_memory_replace(ns, body, ctx):
            now = datetime.utcnow()
            agent = get_agent(ctx)
            async with ctx.session_ctx() as session:
                item = await session.scalar(
                    sa.select(WorkingMemoryItem)
                    .where(WorkingMemoryItem.deleted_at == None)
                    .where(WorkingMemoryItem.session_id == ctx.session_id)
                    .where(WorkingMemoryItem.agent == agent)
                    .where(WorkingMemoryItem.item_id == ns.item_id)
                    .limit(1)
                )
                if item is None:
                    return f"No working memory item with ID {ns.item_id}"

                item.value = ns.item
                item.updated_at = now
                item.updated_by_event_id = ctx.event_id
                session.add(item)
                await session.commit()

                return None

        return [
            working_memory_add,
            working_memory_rm,
            working_memory_replace,
        ]
