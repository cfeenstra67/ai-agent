import abc
import dataclasses as dc
from typing import List, Optional, Iterator


@dc.dataclass(frozen=True)
class CommandArgs:
    """
    """
    command: str
    args: List[str]
    body: Optional[str]


class CommandParser(abc.ABC):
    """
    """
    @abc.abstractmethod
    def parse(self, message: str) -> Iterator[CommandArgs]:
        """
        """
        raise NotImplementedError
