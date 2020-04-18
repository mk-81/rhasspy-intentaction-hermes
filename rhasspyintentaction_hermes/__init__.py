
"""Hermes MQTT server for script/remote-http/homeassistant actions"""
import logging
import os
import typing
import json

from enum import Enum
from urllib.parse import urljoin
from uuid import uuid4

from rhasspyhermes.base import Message
from rhasspyhermes.client import GeneratorType, HermesClient
from rhasspyhermes.handle import HandleToggleOff, HandleToggleOn
from rhasspyhermes.nlu import NluIntent
from rhasspyhermes.tts import TtsSay

from .ActionManager import ActionManager

if "PYDEV_ACTIVE" in os.environ.keys():
    import sys
    pydev_path = r'/home/{USER}/pysrc'.replace("{USER}", os.environ["USER"])
    sys.path.append(pydev_path)
    import pydevd
    pydevd.settrace(os.environ.get("PYDEV_REMOTE_MACHINE")) # replace IP with address of Eclipse host machine

_LOGGER = logging.getLogger(__name__)

# -----------------------------------------------------------------------------

class IntentActionHermesMqtt(HermesClient):
    """Hermes MQTT server for Rhasspy generic intent handling."""

    def __init__(
        self,
        client,
        site_ids: typing.Optional[typing.List[str]] = None
    ):
        super().__init__("rhasspyintentaction_hermes", client, site_ids=site_ids)

        self.subscribe(NluIntent, HandleToggleOn, HandleToggleOff)

        self.handle_enabled = True
        
        self.intend_map: typing.Dict[str, typing.Dict] = {}
        
        self.action_manager = ActionManager()
        
        self.load( )
    # -------------------------------------------------------------------------
    

    def load(self):
        config_path = os.environ["RHASSPY_PROFILE_DIR"]
        
        used_action_names = set()
        
        try:
            with open(os.path.join(config_path, "intent_map.json") , 'r') as intent_to_action_map_file:
                intent_to_action_map = json.load(intent_to_action_map_file)
        except Exception as e:
            intent_to_action_map = None
            _LOGGER.error("Error loading intend map: " + str(e) )
            
        if not intent_to_action_map:
            return
            
        
        for intend_name, intend_def in intent_to_action_map.items():
            action_name = intend_def.get("action")
            self.intend_map[intend_name] = {
                "action_name" : action_name 
            }
            if (action_name != None):
                used_action_names.add(action_name)
                
        self.action_manager.set_used_action_names(used_action_names)
        self.action_manager.prepare()

        for intend_name, intend_def in self.intend_map.items():
            intend_def["handler"] = self.action_manager.get_action_handler_instance(intend_def["action_name"])
   
# -------------------------------------------------------------------------


    async def dispatch_event(
        self, nlu_intent: NluIntent
    ) -> typing.AsyncIterable[TtsSay]:
        intend_map = self.intend_map.get(nlu_intent.intent.intent_name)
        if not intend_map:
            intend_map = self.intend_map.get("")
            
        if intend_map and intend_map["handler"]:
            response_dict = await intend_map["handler"].handle_intent(nlu_intent)
            
            if response_dict:
                tts_text = response_dict.get("speech", {}).get("text", "")
                if tts_text:
                    # Forward to TTS system
                    yield TtsSay(
                        text=tts_text,
                        id=str(uuid4()),
                        site_id=nlu_intent.site_id,
                        session_id=nlu_intent.session_id,
                    )

    # -------------------------------------------------------------------------


    async def on_message(
        self,
        message: Message,
        site_id: typing.Optional[str] = None,
        session_id: typing.Optional[str] = None,
        topic: typing.Optional[str] = None,
    ) -> GeneratorType:
        """Received message from MQTT broker."""
        if isinstance(message, NluIntent):
            if not self.handle_enabled:
                _LOGGER.debug("Intent handling is disabled")
                return
            
            async for intent_result in self.dispatch_event(message):
                yield intent_result            

        elif isinstance(message, HandleToggleOn):
            self.handle_enabled = True
            _LOGGER.debug("Intent handling enabled")
        elif isinstance(message, HandleToggleOff):
            self.handle_enabled = False
            _LOGGER.debug("Intent handling disabled")
        else:
            _LOGGER.warning("Unexpected message: %s", message)
