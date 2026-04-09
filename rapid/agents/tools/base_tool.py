from __future__ import annotations
"""BaseTool — abstract base every agent tool must implement."""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    name: str = ""          # unique identifier used in tools_available lists
    description: str = ""  # plain-language description injected into agent prompts

    @abstractmethod
    async def run(self, **kwargs) -> str:
        """
        Execute the tool and return a natural-language result string.
        Raw data (rows, chunks, schema) must NEVER be returned.
        """
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r})"
