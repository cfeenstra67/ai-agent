import shlex
import textwrap
import re
from typing import Iterator, List

from ai_agent.agent import CommandParser, CommandRequest, Context, AIAgentError
from ai_agent.modular_agent import MessageProvider, AgentMessage


class DefaultCommandParser(CommandParser, MessageProvider):
    """
    """
    docs = textwrap.dedent("""
    In your response, any line that begins with $$ will be interpreted as a command.
    You may issue multiple commands at the same time.
    Any line that does not begin with $$ will be ignored and can be used to add context
    to commands or talk through what you are doing. Please keep your answers short though.
    The syntax for commands is a subset of bash syntax. For commands that require a body,
    you can use the bash <<EOF syntax, for example:
    $$ my-command -p 123 <<EOF
    This is the body
    EOF
    """).strip()

    async def get_messages(self, agent: str, ctx: Context) -> List[AgentMessage]:
        return [AgentMessage(self.docs)]

    def parse(self, result: str) -> Iterator[CommandRequest]:
        rest = result

        while rest:
            line, *other_parts = rest.split("\n", 1)
            if other_parts:
                rest = other_parts[0].lstrip("\r")
            else:
                rest = ""
            
            if not line.startswith("$$"):
                continue
                
            line = line[2:]

            line_match = re.search(r"^(.+)(<<[A-Z]+)\s*$", line)
            body = None
            if line_match:
                line, body_pipe = line_match.groups()
                body_key = body_pipe[2:]
                try:
                    end = rest.index("\n" + body_key)
                except ValueError as err:
                    raise NoBodyEndTag(body_key) from err
            
                body = rest[:end - 1]
                rest = rest[end + len(body_key) + 1:]

            command, *args = shlex.split(line)
            yield CommandRequest(command, args, body)


class NoBodyEndTag(AIAgentError):
    """
    """
    def __init__(self, tag: str) -> None:
        self.tag = tag
        super().__init__(f"No body end tag found: '{tag}'")
