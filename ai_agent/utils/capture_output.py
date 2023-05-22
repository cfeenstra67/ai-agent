import contextlib
import io
from typing import Callable

def capture_output(func: Callable[[], None]) -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        func()
        return out.getvalue()
