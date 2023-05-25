import textwrap

import openai

from ai_agent.agent import Runner, task_queue_empty, AgentMessage
from ai_agent.agent_history import AgentHistoryService
from ai_agent.chatgpt_chatter import ChatGPTChatter
from ai_agent.chat_room_service import ChatRoomService
from ai_agent.command_docs import CommandDocsService
from ai_agent.default_command_parser import DefaultCommandParser
from ai_agent.interactive_chatter import InteractiveChatter
from ai_agent.modular_agent import ModularAgent, GlobCommandFilter
from ai_agent.utils.blinker import iterate_signals
from ai_agent.utils.sqlalchemy import merge_metadatas
from ai_agent.working_memory_service import WorkingMemoryService


with open(".openai-key") as f:
    openai.api_key = f.read()


async def queue_messages(runner: Runner):
    ctx = runner.context()

    async for _ in iterate_signals(task_queue_empty, runner):
        event = await ctx.queue_agent("agent-1", "Nothing is running, please give another command")
        try:
            result = await ctx.wait_for_event(event)
            print("RESULT", result)
        except Exception as err:
            print("ERROR", err)


async def runner(session_id, engine, created):
    working_memory = WorkingMemoryService()
    agent_history = AgentHistoryService()
    docs = CommandDocsService()
    chat_room = ChatRoomService()

    metadata = merge_metadatas(
        working_memory.get_sqlalchemy_metadata(),
        agent_history.get_sqlalchemy_metadata(),
        chat_room.get_sqlalchemy_metadata(),
    )
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)
    
    parser = DefaultCommandParser()

    agent_1 = ModularAgent(
        "agent-1",
        InteractiveChatter(),
        message_providers=[
            AgentMessage(
                "You are a secret agent",
                "system"
            ),
            parser,
            docs,
            working_memory,
            agent_history,
        ],
        command_filters=[
            # GlobCommandFilter(["workmem-*", "help"])
        ]
    )

    agent_2 = ModularAgent(
        "agent-2",
        # InteractiveChatter(),
        ChatGPTChatter(),
        message_providers=[
            AgentMessage(
                textwrap.dedent(
                    """
                    You are are an autonomous agent whose purpose
                    is to socialize with your coworkers. After this
                    message there will be a series of informational messages,
                    then you'll be asked to respond.
                    """
                ).strip(),
                "system"
            ),
            parser,
            docs,
            working_memory,
            agent_history,
        ],
        command_filters=[
            # GlobCommandFilter(["workmem-*", "help"])
        ]
    )

    runner = Runner(
        session_id,
        engine,
        command_parser=parser,
        agents=[agent_1, agent_2],
        agent_middlewares=[agent_history],
        commands=[
            *working_memory.commands(),
            docs.help_command(),
            chat_room.chat_command(),
        ]
    )

    if created:
        ctx = runner.context()
        for agent in [agent_1, agent_2]:
            await ctx.queue_agent(agent.name, "Please enter your first command")

    return runner,
    # return runner, queue_messages(runner)
