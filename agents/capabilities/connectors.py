"""
connectors.py — Production connectors for external APIs and data sources.

Implements 4 critical connectors:
  1. SalesforceConnector — CRM data (deals, accounts, contacts)
  2. HubSpotConnector — Marketing/sales data (contacts, companies, deals)
  3. SlackConnector — Messaging (send/read messages)
  4. RealtimeConnector — Live data feeds (metrics, alerts)

All connectors inherit from BaseConnector and implement required methods.
"""

import asyncio
import logging
import json
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import aiohttp
from abc import abstractmethod

from agents.capabilities.base_connector import (
    BaseConnector,
    ConnectorConfig,
    APIConnector,
    MessagingConnector,
)

logger = logging.getLogger(__name__)


class SalesforceConnector(APIConnector):
    """
    Salesforce CRM connector.

    Provides access to:
      - Opportunities (deals)
      - Accounts (companies)
      - Contacts (people)
      - Tasks, Events

    Requires: SALESFORCE_URL, SALESFORCE_CLIENT_ID, SALESFORCE_CLIENT_SECRET
    """

    def __init__(self, config: ConnectorConfig):
        """Initialize Salesforce connector."""
        super().__init__(config)
        self.base_url = config.settings.get('salesforce_url', '')
        self.client_id = config.credentials.get('client_id', '')
        self.client_secret = config.credentials.get('client_secret', '')
        self.access_token = None
        self.token_expires_at = None

    async def _do_connect(self) -> bool:
        """Authenticate with Salesforce OAuth."""
        try:
            async with aiohttp.ClientSession() as session:
                auth_url = f"{self.base_url}/services/oauth2/token"
                data = {
                    'grant_type': 'client_credentials',
                    'client_id': self.client_id,
                    'client_secret': self.client_secret,
                }

                async with session.post(auth_url, data=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        self.access_token = result.get('access_token')
                        self.token_expires_at = datetime.now() + timedelta(
                            seconds=result.get('expires_in', 3600)
                        )
                        logger.info("Salesforce connected")
                        return True
                    else:
                        logger.error(f"Salesforce auth failed: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"Salesforce connection error: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if Salesforce is accessible."""
        try:
            await self._ensure_token()
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.access_token}'}
                url = f"{self.base_url}/services/data/v57.0/"

                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    return resp.status == 200
        except Exception as e:
            logger.error(f"Salesforce health check failed: {e}")
            return False

    async def call(self, endpoint: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
        """
        Call Salesforce API.

        Args:
            endpoint: API endpoint (e.g., '/services/data/v57.0/query')
            method: HTTP method (GET, POST, PATCH, DELETE)
            **kwargs: Query parameters or body data

        Returns:
            API response as dict
        """
        await self._ensure_token()

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {self.access_token}',
                    'Content-Type': 'application/json',
                }

                url = f"{self.base_url}{endpoint}"
                timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)

                for attempt in range(self.config.max_retries):
                    try:
                        async with session.request(method, url, headers=headers, json=kwargs, timeout=timeout) as resp:
                            if resp.status == 200:
                                return await resp.json()
                            elif resp.status == 401:
                                # Token expired, refresh
                                await self._refresh_token()
                                continue
                            else:
                                logger.error(f"Salesforce API error: {resp.status}")
                                return {'error': f'Status {resp.status}'}
                    except asyncio.TimeoutError:
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        raise

        except Exception as e:
            logger.error(f"Salesforce API call failed: {e}")
            return {'error': str(e)}

    async def query_opportunities(self, filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Query open opportunities (deals).

        Args:
            filters: Filter conditions (e.g., {'stage': 'Negotiation', 'amount_min': 50000})

        Returns:
            List of opportunities
        """
        soql = "SELECT Id, Name, Amount, StageName, CloseDate FROM Opportunity WHERE IsClosed = false"

        if filters:
            if 'stage' in filters:
                soql += f" AND StageName = '{filters['stage']}'"
            if 'amount_min' in filters:
                soql += f" AND Amount >= {filters['amount_min']}"

        result = await self.call(
            '/services/data/v57.0/query',
            q=soql
        )

        return result.get('records', [])

    async def query_accounts(self, search: str = '') -> List[Dict[str, Any]]:
        """
        Query accounts (companies).

        Args:
            search: Search term (company name)

        Returns:
            List of accounts
        """
        soql = "SELECT Id, Name, Industry, AnnualRevenue, Website FROM Account"

        if search:
            soql += f" WHERE Name LIKE '%{search}%'"

        result = await self.call(
            '/services/data/v57.0/query',
            q=soql
        )

        return result.get('records', [])

    async def _ensure_token(self) -> None:
        """Refresh token if expired."""
        if not self.access_token or (self.token_expires_at and datetime.now() >= self.token_expires_at):
            await self._refresh_token()

    async def _refresh_token(self) -> None:
        """Refresh OAuth token."""
        await self._do_connect()


class HubSpotConnector(APIConnector):
    """
    HubSpot connector.

    Provides access to:
      - Contacts
      - Companies
      - Deals
      - Pipelines

    Requires: HUBSPOT_API_KEY
    """

    def __init__(self, config: ConnectorConfig):
        """Initialize HubSpot connector."""
        super().__init__(config)
        self.api_key = config.credentials.get('api_key', '')
        self.base_url = 'https://api.hubapi.com'

    async def _do_connect(self) -> bool:
        """Verify HubSpot API key is valid."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.api_key}'}
                url = f"{self.base_url}/crm/v3/objects/contacts"

                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        logger.info("HubSpot connected")
                        return True
                    else:
                        logger.error(f"HubSpot auth failed: {resp.status}")
                        return False
        except Exception as e:
            logger.error(f"HubSpot connection error: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if HubSpot is accessible."""
        return await self._do_connect()

    async def call(self, endpoint: str, method: str = "GET", **kwargs) -> Dict[str, Any]:
        """
        Call HubSpot API.

        Args:
            endpoint: API endpoint path
            method: HTTP method
            **kwargs: Parameters or body

        Returns:
            API response
        """
        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                }

                url = f"{self.base_url}{endpoint}"
                timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)

                async with session.request(method, url, headers=headers, json=kwargs, timeout=timeout) as resp:
                    if resp.status in [200, 201]:
                        return await resp.json()
                    else:
                        logger.error(f"HubSpot API error: {resp.status}")
                        return {'error': f'Status {resp.status}'}

        except Exception as e:
            logger.error(f"HubSpot API call failed: {e}")
            return {'error': str(e)}

    async def search_contacts(self, query: str) -> List[Dict[str, Any]]:
        """
        Search contacts by name/email.

        Args:
            query: Search term

        Returns:
            List of matching contacts
        """
        filter_group = {
            'filters': [
                {
                    'propertyName': 'firstname',
                    'operator': 'CONTAINS_TOKEN',
                    'value': query
                },
                {
                    'propertyName': 'lastname',
                    'operator': 'CONTAINS_TOKEN',
                    'value': query
                }
            ],
            'filterOperator': 'OR'
        }

        result = await self.call(
            '/crm/v3/objects/contacts/search',
            method='POST',
            **filter_group
        )

        return result.get('results', [])

    async def get_deals(self, pipeline_id: str = None) -> List[Dict[str, Any]]:
        """
        Get deals from a pipeline.

        Args:
            pipeline_id: HubSpot pipeline ID (optional)

        Returns:
            List of deals
        """
        result = await self.call(
            '/crm/v3/objects/deals',
            limit=100,
            archived=False
        )

        return result.get('results', [])


class SlackConnector(MessagingConnector):
    """
    Slack connector.

    Provides access to:
      - Send messages to channels
      - Read channel messages
      - User presence
      - Thread replies

    Requires: SLACK_BOT_TOKEN
    """

    def __init__(self, config: ConnectorConfig):
        """Initialize Slack connector."""
        super().__init__(config)
        self.bot_token = config.credentials.get('bot_token', '')
        self.base_url = 'https://slack.com/api'

    async def _do_connect(self) -> bool:
        """Verify Slack bot token is valid."""
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.bot_token}'}
                url = f"{self.base_url}/auth.test"

                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            logger.info("Slack connected")
                            return True

                logger.error("Slack auth failed")
                return False
        except Exception as e:
            logger.error(f"Slack connection error: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if Slack is accessible."""
        return await self._do_connect()

    async def send_message(self, channel: str, message: str) -> bool:
        """
        Send a message to a Slack channel.

        Args:
            channel: Channel ID or name
            message: Message text

        Returns:
            True if sent successfully
        """
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.bot_token}'}
                url = f"{self.base_url}/chat.postMessage"

                data = {
                    'channel': channel,
                    'text': message,
                }

                async with session.post(url, headers=headers, json=data) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            logger.info(f"Message sent to {channel}")
                            return True

                logger.error("Failed to send Slack message")
                return False

        except Exception as e:
            logger.error(f"Slack send message failed: {e}")
            return False

    async def read_channel(self, channel: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Read messages from a Slack channel.

        Args:
            channel: Channel ID or name
            limit: Max messages to read

        Returns:
            List of messages
        """
        try:
            async with aiohttp.ClientSession() as session:
                headers = {'Authorization': f'Bearer {self.bot_token}'}
                url = f"{self.base_url}/conversations.history"

                params = {
                    'channel': channel,
                    'limit': limit,
                }

                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        if result.get('ok'):
                            return result.get('messages', [])

                logger.error("Failed to read Slack channel")
                return []

        except Exception as e:
            logger.error(f"Slack read channel failed: {e}")
            return []


class RealtimeConnector(BaseConnector):
    """
    Real-time data connector.

    Provides live data streams:
      - Metrics (revenue, signups, etc)
      - Alerts (system health, thresholds)
      - Event feeds (sales, support tickets)

    This is a stub that connects to internal data streams.
    """

    def __init__(self, config: ConnectorConfig):
        """Initialize real-time connector."""
        super().__init__(config)
        self._data_cache = {}
        self._last_update = {}

    async def _do_connect(self) -> bool:
        """Initialize real-time data streams."""
        try:
            logger.info("Real-time connector initialized")
            return True
        except Exception as e:
            logger.error(f"Real-time connector failed: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if data streams are flowing."""
        # In production, check if data is being updated
        return self._is_connected

    async def subscribe(self, stream_name: str, callback=None) -> None:
        """
        Subscribe to a real-time data stream.

        Args:
            stream_name: Name of stream (e.g., 'revenue', 'support_tickets')
            callback: Async callback function to call when data arrives
        """
        if stream_name not in self._data_cache:
            self._data_cache[stream_name] = []
            logger.info(f"Subscribed to {stream_name}")

    async def get_latest(self, stream_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get latest data from a stream.

        Args:
            stream_name: Stream name
            limit: Max items to return

        Returns:
            List of latest data points
        """
        return self._data_cache.get(stream_name, [])[-limit:]

    async def publish(self, stream_name: str, data: Dict[str, Any]) -> bool:
        """
        Publish data to a stream (for testing).

        Args:
            stream_name: Stream name
            data: Data to publish

        Returns:
            True if published
        """
        if stream_name not in self._data_cache:
            self._data_cache[stream_name] = []

        self._data_cache[stream_name].append({
            'timestamp': datetime.now().isoformat(),
            **data
        })

        self._last_update[stream_name] = datetime.now()
        return True
