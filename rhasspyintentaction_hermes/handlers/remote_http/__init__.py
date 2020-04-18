"""Hermes MQTT server for Rhasspy remote server"""
import json
import logging
import ssl
import typing
import os
from uuid import uuid4

import aiohttp
from rhasspyhermes.nlu import NluIntent
from rhasspyhermes.tts import TtsSay
from multiprocessing.util import _logger

_LOGGER = logging.getLogger(__name__)


class RemoteHttpIntendHandler():
    def __init__(
        self,
        environment
    ):
        self._initialized = False
        self._environment = environment
        
        # Async HTTP
        self._http_session: typing.Optional[aiohttp.ClientSession] = None

# -----------------------------------------------------------------------------


    def initialize(self):
        def_file_name = os.path.join(self._environment.self_directory, "def.json")

        try:
            with open(def_file_name , 'r') as def_file:
                definition = json.load(def_file)
        except Exception as e:
            _LOGGER.error(f"Error loading definition in {def_file_name}: " + str(e))
            return
                
        if not definition:
            return 
        
        self.handle_url = definition.get("handle_url")

        # SSL
        certfile = definition.get("certfile")
        keyfile  = definition.get("keyfile")

        self.ssl_context = ssl.SSLContext()
        
        if certfile:
            _LOGGER.debug("Using SSL with certfile=%s, keyfile=%s", certfile, keyfile)
            self.ssl_context.load_cert_chain(certfile, keyfile)
            
        self._initialized = True

# -----------------------------------------------------------------------------


    @property
    def http_session(self):
        """Get or create async HTTP session"""
        if self._http_session is None:
            self._http_session = aiohttp.ClientSession()

        return self._http_session

# -----------------------------------------------------------------------------


    async def handle_intent(
        self, intent: NluIntent
    ) -> typing.Dict[str, typing.Any]:
        """Handle intent with remote server or local command."""
        
        if not self._initialized:
            return
        
        try:
            intent_dict = intent.to_rhasspy_dict()

            # Add site_id
            intent_dict["site_id"] = intent.site_id

            if self.handle_url:
                # Remote server
                _LOGGER.debug(self.handle_url)

                async with self.http_session.post(
                    self.handle_url, json=intent_dict, ssl=self.ssl_context
                ) as response:
                    response.raise_for_status()
                    response_dict = await response.json()

                # Check for speech response
                return response_dict
            else:
                _LOGGER.warning("Can't handle intent. No handle URL.")

        except Exception as e:
            _LOGGER.exception("handle_intent: " + str(e) )
