"""Hermes MQTT server for Rhasspy fuzzywuzzy"""
import logging
import ssl
import typing
import os
from urllib.parse import urljoin
from uuid import uuid4

import aiohttp
from rhasspyhermes.nlu import NluIntent
from rhasspyhermes.tts import TtsSay

# -----------------------------------------------------------------------------

_LOGGER = logging.getLogger(__name__)


class HandleType():
    """Method for handling intents."""

    EVENT = "event"
    INTENT = "intent"


# -----------------------------------------------------------------------------


class HomeAssistantIntendHandler():
    """Hermes MQTT server for Rhasspy intent handling with Home Assistant."""

    def __init__(
        self,
        environment
    ):
        self._initialized = False
        self._environment = environment

        # Async HTTP
        self._http_session: typing.Optional[aiohttp.ClientSession] = None
        
    # -------------------------------------------------------------------------


    def initialize(self):
        """Initialize handler"""
        def_file_name = os.path.join(self._environment.self_directory, "def.json")

        try:
            with open(def_file_name, 'r') as def_file:
                definition = json.load(def_file)
        except Exception as e:
            _LOGGER.error(f"Error loading definition in {def_file_name}: " + str(e))
            return
                
        if not definition:
            return 
        
        self.url               = definition.get("url")
        self.access_token      = definition.get("access_token")
        self.api_password      = definition.get("api_password")
        self.event_type_format = definition.get("event_type_format")
        self.handle_type       = definition.get("handle_type")

        # SSL
        certfile = definition.get("certfile")
        keyfile  = definition.get("keyfile")

        #ssl
        self.ssl_context = ssl.SSLContext()
        if certfile:
            _LOGGER.debug("Using SSL with certfile=%s, keyfile=%s", certfile, keyfile)
            self.ssl_context.load_cert_chain(certfile, keyfile)
            
        self._initialized = True

    # -------------------------------------------------------------------------


    @property
    def http_session(self):
        """Get or create async HTTP session"""
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()

        return self._http_session

    # -------------------------------------------------------------------------


    async def handle_intent(
        self, intent: NluIntent
    ) -> typing.Dict[str, typing.Any]:
        """Handle intent with Home Assistant."""
        
        if not self._initialized:
            return
        
        try:
            if self.handle_type == HandleType.EVENT:
                await self.handle_home_assistant_event(intent)
            
            elif self.handle_type == HandleType.INTENT:
                response_dict = await self.handle_home_assistant_intent(intent)
                assert response_dict, f"No response from {self.url}"

            else:
                raise ValueError(f"Unsupported handle_type (got {self.handle_type})")
        except Exception as e:
            _LOGGER.exception("handle_intent: " + e)

    # -------------------------------------------------------------------------


    async def handle_home_assistant_event(self, intent: NluIntent):
        """POSTs an event to Home Assistant's /api/events endpoint."""
        try:
            # Create new Home Assistant event
            event_type = self.event_type_format.format(intent.intent.intent_name)
            slots: typing.Dict[str, typing.Any] = {}

            if intent.slots:
                for slot in intent.slots:
                    slots[slot.slot_name] = slot.value["value"]

            # Add meta slots
            slots["_text"] = intent.input
            slots["_raw_text"] = intent.raw_input
            slots["_intent"] = intent.to_dict()

            # Send event
            post_url = urljoin(self.url, "api/events/" + event_type)
            headers = self.get_hass_headers()

            _LOGGER.debug(post_url)

            # No response expected
            async with self.http_session.post(
                post_url, json=slots, headers=headers, ssl=self.ssl_context
            ) as response:
                response.raise_for_status()
        except Exception as e:
            _LOGGER.exception("handle_home_assistant_event: " + e)

    # -------------------------------------------------------------------------


    async def handle_home_assistant_intent(
        self, intent: NluIntent
    ) -> typing.Dict[str, typing.Any]:
        """POSTs a JSON intent to Home Assistant's /api/intent/handle endpoint."""
        try:
            slots: typing.Dict[str, typing.Any] = {}

            if intent.slots:
                for slot in intent.slots:
                    slots[slot.slot_name] = slot.value["value"]

            # Add meta slots
            slots["_text"] = intent.input
            slots["_raw_text"] = intent.raw_input
            slots["_intent"] = intent.to_dict()

            hass_intent = {"name": intent.intent.intent_name, "data": slots}

            # POST intent JSON
            post_url = urljoin(self.url, "api/intent/handle")
            headers = self.get_hass_headers()

            _LOGGER.debug(post_url)

            # JSON response expected with optional speech
            async with self.http_session.post(
                post_url, json=hass_intent, headers=headers, ssl=self.ssl_context
            ) as response:
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            _LOGGER.exception("handle_home_assistant_intent: " + str(e))

        # Empty response
        return {}

    # -------------------------------------------------------------------------


    def get_hass_headers(self) -> typing.Dict[str, str]:
        """Gets HTTP authorization headers for Home Assistant POST."""
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}

        if self.api_password:
            return {"X-HA-Access": self.api_password}

        hassio_token = os.environ.get("HASSIO_TOKEN")
        if hassio_token:
            return {"Authorization": f"Bearer {hassio_token}"}

        # No headers
        return {}

    # -------------------------------------------------------------------------