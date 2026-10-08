from __future__ import annotations

from abc import ABC, abstractmethod

from ..contracts import Contract

Board = dict[str, Contract]


class Agent(ABC):
    """One role in the QA organisation.

    An agent reads the contracts named in ``consumes`` from the shared board and
    returns exactly one contract whose schema id is ``produces``. Agents never
    talk to each other directly; the orchestrator moves documents between them.
    """

    name: str
    consumes: tuple[str, ...] = ()
    produces: str

    @abstractmethod
    def run(self, board: Board) -> Contract: ...
