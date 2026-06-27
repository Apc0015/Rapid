"""
base_connector.py — Base class for all data connectors.

Connectors are the "hands" that skills use to access external data sources.
A skill might need multiple connectors (e.g., sql + web + slack).

Examples:
    - DatabaseConnector: Query SQL databases
    - DocumentConnector: Search vector stores (FAISS, Qdrant)
    - WebConnector: Search the internet
    - SalesforceConnector: Access Salesforce CRM
    - SlackConnector: Post to Slack, read channels
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ConnectorConfig:
    """Configuration for a connector."""

    name: str                           # Unique identifier (e.g., 'salesforce')
    type: str                           # Type (e.g., 'crm', 'database', 'messaging')
    enabled: bool = True                # Is this connector available?
    credentials: Dict[str, str] = field(default_factory=dict)  # Auth info (kept secure)
    settings: Dict[str, Any] = field(default_factory=dict)  # Tunable settings
    max_retries: int = 3
    timeout_seconds: int = 30


class BaseConnector(ABC):
    """
    Abstract base class for all data connectors.

    Connectors provide access to external data sources (databases, APIs, documents, etc).
    Skills use connectors to fetch the data they need.

    Attributes:
        name: Unique identifier (e.g., 'database', 'salesforce', 'web')
        type: Category (e.g., 'database', 'crm', 'web', 'messaging', 'document_store')
        enabled: Whether this connector is active
    """

    def __init__(self, config: ConnectorConfig):
        """
        Initialize connector with configuration.

        Args:
            config: ConnectorConfig with name, type, credentials, etc.
        """
        self.name = config.name
        self.type = config.type
        self.enabled = config.enabled
        self.config = config
        self._is_connected = False

    async def connect(self) -> bool:
        """
        Establish connection to the data source.

        Called once at startup. Must be implemented by subclasses.

        Returns:
            True if connection successful, False otherwise
        """
        self._is_connected = await self._do_connect()
        return self._is_connected

    @abstractmethod
    async def _do_connect(self) -> bool:
        """
        Actual connection logic (implement in subclass).

        Returns:
            True if connected, False otherwise
        """
        pass

    async def disconnect(self) -> None:
        """Disconnect from the data source."""
        self._is_connected = False

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if connector is healthy (can reach the data source).

        Returns:
            True if healthy, False otherwise
        """
        pass

    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._is_connected

    def get_config(self) -> Dict[str, Any]:
        """Return connector configuration (for admin display)."""
        return {
            'name': self.name,
            'type': self.type,
            'enabled': self.enabled,
            'connected': self._is_connected,
            'timeout_seconds': self.config.timeout_seconds,
            'max_retries': self.config.max_retries,
        }

    def __repr__(self) -> str:
        """String representation."""
        status = "connected" if self._is_connected else "disconnected"
        return f"<{self.name}({self.type}) [{status}]>"


class DatabaseConnector(BaseConnector):
    """Base class for database connectors (SQL databases)."""

    async def query(self, sql: str) -> List[Dict[str, Any]]:
        """
        Execute a SQL query.

        Args:
            sql: SQL SELECT query (read-only, validated)

        Returns:
            List of result rows as dicts
        """
        raise NotImplementedError("Subclass must implement query()")


class DocumentConnector(BaseConnector):
    """Base class for document/vector store connectors."""

    async def search(self, query: str, dept_tag: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Search documents by semantic similarity.

        Args:
            query: Search query (natural language)
            dept_tag: Department for isolated search
            top_k: Number of results to return

        Returns:
            List of matching documents with scores
        """
        raise NotImplementedError("Subclass must implement search()")


class APIConnector(BaseConnector):
    """Base class for API connectors (Salesforce, HubSpot, etc)."""

    async def call(self, endpoint: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
        """
        Make an API call.

        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST, etc)
            **kwargs: Additional parameters

        Returns:
            API response as dict
        """
        raise NotImplementedError("Subclass must implement call()")


class MessagingConnector(BaseConnector):
    """Base class for messaging connectors (Slack, Teams, etc)."""

    async def send_message(self, channel: str, message: str) -> bool:
        """
        Send a message to a channel.

        Args:
            channel: Channel name or ID
            message: Message text

        Returns:
            True if sent successfully
        """
        raise NotImplementedError("Subclass must implement send_message()")

    async def read_channel(self, channel: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Read messages from a channel.

        Args:
            channel: Channel name or ID
            limit: Max messages to read

        Returns:
            List of messages
        """
        raise NotImplementedError("Subclass must implement read_channel()")


class ConnectorRegistry:
    """
    Central registry for all connectors.

    Keeps track of available connectors, manages connections, health checks.
    """

    def __init__(self):
        """Initialize connector registry."""
        self._connectors: Dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        """
        Register a connector.

        Args:
            connector: Connector instance to register
        """
        self._connectors[connector.name] = connector

    def get(self, name: str) -> Optional[BaseConnector]:
        """
        Get a connector by name.

        Args:
            name: Connector name (e.g., 'database', 'salesforce')

        Returns:
            Connector instance or None if not found
        """
        return self._connectors.get(name)

    def list(self) -> List[BaseConnector]:
        """Get all registered connectors."""
        return list(self._connectors.values())

    def list_enabled(self) -> List[BaseConnector]:
        """Get only enabled connectors."""
        return [c for c in self._connectors.values() if c.enabled]

    async def connect_all(self) -> Dict[str, bool]:
        """
        Connect all registered connectors.

        Returns:
            Dict of connector_name -> success (True/False)
        """
        results = {}
        for name, connector in self._connectors.items():
            try:
                results[name] = await connector.connect()
            except Exception as e:
                logger.warning("Failed to connect %s: %s", name, e)
                results[name] = False
        return results

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Health check all connectors.

        Returns:
            Dict of connector_name -> is_healthy (True/False)
        """
        results = {}
        for name, connector in self._connectors.items():
            try:
                results[name] = await connector.health_check()
            except Exception as e:
                logger.warning("Health check failed for %s: %s", name, e)
                results[name] = False
        return results

    def __repr__(self) -> str:
        """String representation."""
        return f"<ConnectorRegistry({len(self._connectors)} connectors)>"
