"""Hermes MQTT server for Rhasspy remote server"""
import logging
import typing
import ssl
import asyncio
import json
import os
from uuid import uuid4

from rhasspyhermes.nlu import NluIntent
from rhasspyhermes.tts import TtsSay

_LOGGER = logging.getLogger(__name__)


class CommandIntendHandler():
    def __init__(
        self,
        environment
    ):
        self._initialized = False
        self._environment = environment
        self.handle_command = None

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
        
        self.handle_command = self.expand_command(definition.get("command"), definition.get("parameters") )
        
        self._initialized = True

# -----------------------------------------------------------------------------


    def expand_command(self, handle_command, parameters):
        if not handle_command:
            return None
        
        if handle_command.startswith("."):
            cmd = handle_command.replace(".", self._environment.self_directory, 1)
            
        #ToDo optional resolve parameters with type (cmd --p1 a --p2 b):
        # * str                     e.g. --p1 a --p2 b  
        # * tuple                   e.g. ("--1 a", "--p2 b")
        # * list[str]               e.g. ["--p1 a", "--p2 b"]
        # * list[tuple(str, Any)]   e.g. [("--p1", "a"), ("--p2", "b") ]
        # * dict                    e.g. { "--p1" : "a", "--p2" : "b" } 
        return cmd

# -----------------------------------------------------------------------------


    async def handle_intent(
        self, intent: NluIntent
    ) -> typing.Dict[str, typing.Any]:
        """Handle intent with local command."""
        
        if not self._initialized:
            return

        try:
            if self.handle_command:
                intent_json = json.dumps(intent.to_rhasspy_dict())

                # Local handling command
                _LOGGER.debug(self.handle_command)
                
                env = os.environ.copy() # for new Env-Varialbles

                proc = await asyncio.create_subprocess_exec(
                    self.handle_command,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=self._environment.self_directory,
                    env=env,
                )

                output, error = await proc.communicate(intent_json.encode())
                rc = proc.returncode

                if error:
                    _LOGGER.debug(error.decode())
                
                if rc == 0:
                    try:
                        response_dict = json.loads(output)
                        return response_dict
                    except Exception as e:
                        _LOGGER.debug(str(e))
                        
            else:
                _LOGGER.warning("Can't handle intent. No handle command.")

        except Exception as e:
            _LOGGER.exception("handle_intent: " + str(e))

        return None
