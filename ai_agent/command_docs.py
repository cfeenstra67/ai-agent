import argparse
import textwrap
from typing import List

from ai_agent.agent import Context, AgentMessage, Command, InvalidCommand
from ai_agent.argparse_command import argparse_command
from ai_agent.event_bus import DEFAULT_PRIORITY
from ai_agent.modular_agent import MessageProvider


class CommandDocsService(MessageProvider):
    """
    """
    initial_message = textwrap.dedent(
        """
        What follows is each command available to you along
        with the usage for each. You can use the `help` command
        to view full documentation for an individual command.
        """
    ).strip()

    async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
        commands = ctx.get_commands(agent)
        lines = [self.initial_message]
        for command in commands:
            docs = command.get_docs()
            lines.append(f"$$ {docs.usage}: {docs.description}")
        return [AgentMessage("\n\n".join(lines))]

    def help_command(
        self,
        name: str = "help",
        priority: int = DEFAULT_PRIORITY + 1
    ) -> Command:

        parser = argparse.ArgumentParser(
            prog=name,
            description="Get documentation for a command",
            add_help=False,
        )
        parser.add_argument(
            "cmd",
            help="Command to get documentation for"
        )

        @argparse_command(parser=parser, priority=priority)
        def help(ns, body, ctx):
            agent_name = None
            if ctx.event is not None and ctx.event.source_type == "agent":
                agent_name = ctx.event.source_destination

            agent_commands = {
                cmd.name: cmd
                for cmd in ctx.get_commands(agent_name)
            }

            if ns.cmd not in agent_commands:
                raise InvalidCommand(ns.cmd)
            
            command = agent_commands[ns.cmd]
            docs = command.get_docs()
            return docs.long_description

        return help
