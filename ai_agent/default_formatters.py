import shlex
import dataclasses as dc
from typing import Any, Dict, List

from ai_agent.agent import AgentResponseValidationError, CommandValidationError, InvalidCommand
from ai_agent.modular_agent import Template


def format_command(command: str, args: List[str]) -> str:
    return " ".join(filter(None, [command, shlex.join(args)]))


@dc.dataclass(frozen=True)
class DefaultResultTemplate(Template):

    max_command_length: int = 100

    async def render(self, scope: Dict[str, Any]) -> str:
        event = scope["event"]
        result = scope["result"]

        cmd = event.destination
        args = event.payload["args"]

        command = format_command(cmd, args)
        if len(command) > self.max_command_length:
            command = command[:self.max_command_length - 3] + "..."

        return f"Result for $$ {command}:\n{result}"


@dc.dataclass(frozen=True)
class DefaultErrorTemplate(Template):

    max_command_length: int = 100

    def _format_error(self, error: Exception, stack: str) -> str:
        if isinstance(error, CommandValidationError):
            cmd_str = format_command(error.command.command, error.command.args)
            if isinstance(error.error, InvalidCommand):
                return f"$$ {cmd_str}: Invalid command"
            return f"$$ {cmd_str}: Invalid arguments: {error.error}"
        return stack

    async def render(self, scope: Dict[str, Any]) -> str:
        error = scope["error"]
        stack = scope["stack"]

        if isinstance(error, AgentResponseValidationError):
            lines = ["That response was invalid. Errors:"]

            for err in error.errors:
                lines.append(self._format_error(
                    err,
                    f"{type(err).__name__}: {err}"
                ))

            return "\n".join(lines)
        
        return self._format_error(error, stack)
