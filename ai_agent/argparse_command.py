import argparse
import contextlib
import io
from functools import wraps
from typing import List, Optional, Any, Callable, Tuple

from ai_agent.agent import Context, AIAgentError
from ai_agent.api import command
from ai_agent.utils.capture_output import capture_output


def validate_args(
    parser: argparse.ArgumentParser,
    args: List[str]
) -> argparse.Namespace:
    """
    """
    out = io.StringIO()

    with contextlib.ExitStack() as stack:
        stack.enter_context(contextlib.redirect_stdout(out))
        stack.enter_context(contextlib.redirect_stderr(out))
        try:
            return parser.parse_args(args)
        except SystemExit:
            raise ArgparseValidationError(out.getvalue().strip())


def argparse_command(
    func: Optional[Callable[[argparse.Namespace, Optional[str], Context], str]] = None,
    *,
    parser: argparse.ArgumentParser,
    priority: Optional[int] = None,
    **kwargs
):
    def dec(f):

        def validate(args, body):
            validate_args(parser, args)
            return priority

        @wraps(f)
        def wrapper(cmd, ctx):
            namespace = validate_args(parser, cmd.args)
            return f(namespace, cmd.body, ctx)

        usage = capture_output(parser.print_usage).split(":", 1)[1].strip()
        description = capture_output(parser.print_help).strip()

        return command(
            wrapper,
            name=parser.prog,
            usage=usage,
            description=parser.description,
            long_description=description,
            validate=validate,
            **kwargs
        )

    if func is None:
        return dec

    return dec(func)


class ArgparseValidationError(AIAgentError):
    
    def __init__(self, output: str) -> None:
        self.output = output
        super().__init__(f"Validation failed: {output}")
