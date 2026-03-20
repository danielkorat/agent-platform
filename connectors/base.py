"""Base connector interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseConnector(ABC):
    """Abstract base for enterprise data connectors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable connector name."""
        ...

    @property
    def is_read_only(self) -> bool:
        """Whether this connector only reads data (no side effects)."""
        return True

    @abstractmethod
    async def search(self, query: str, **kwargs) -> list[dict[str, Any]]:
        """Search this data source."""
        ...

    async def get(self, item_id: str) -> dict[str, Any] | None:
        """Get a specific item by ID."""
        return None

    async def execute_action(self, action: str, params: dict[str, Any]) -> dict[str, Any]:
        """Execute a write action (requires approval). Override if supported."""
        raise NotImplementedError(f"Connector '{self.name}' does not support actions")
