import typing
import os
import json
import importlib
from asyncio.log import logger

class Action():
    def __init__(
        self, 
        data : typing.Dict[str, typing.Any]
    ):
        self._name = data["name"]
        self._handler = data.get("handler")
        
    @property
    def name(self) -> str:
        return self._name
    
    
    @property
    def handler(self):
        return self._handler

    
    @handler.setter
    def handler(self, handler):
        self._handler = handler

# -------------------------------------------------------------------------

class ActionManagerEnvironment():
    def __init__(self):
        self._base_path = os.environ["RHASSPY_PROFILE_DIR"]
        self._action_path = os.path.join(self._base_path, "actions")
        
    def get_action_repository_path(self) -> str:
        return self._action_path
    
    def create_action_environment(
        self, 
        action : Action
    ):
        
        action_manager = self
        
        class ActionEnvironment():
            
            @property
            def self_directory(self):
                return os.path.join(action_manager._action_path, action.name)
        
        return ActionEnvironment()
    
# -------------------------------------------------------------------------
    
    

class ActionManager():
    _buildin_handler_map = {
        "buildin.command" : ".handlers.command.CommandIntendHandler",
        "buildin.remote_http" : ".handlers.remote_http.RemoteHttpIntendHandler" ,
        "buildin.homeassistant" : ".handlers.homeassistant.HomeAssistantIntendHandler"
    }

    def __init__(self):
        super().__init__()
        
        self.used_action_names = None
        self.modules = {}
        self.actions : typing.Dict[str, Action] = {}
        
        self._environment = ActionManagerEnvironment()

    # -------------------------------------------------------------------------


    def set_used_action_names(
        self,
        used_actions : typing.Iterable[str]
    ):
        self.used_action_names = set()
    
        for name in used_actions:
            self.used_action_names.add(name)

    # -------------------------------------------------------------------------
    
    
    def get_module(self, name):
        m = self.modules.get(name)
        if m != None:
            return m
        
        try:
            if name.startswith("."):
                m = importlib.import_module(name, "rhasspyhomeassistant_hermes")
            else:
                m = importlib.import_module(name)
        except Exception as e:
            m = None
            
        self.modules[name] = m
        return m
 
    # -------------------------------------------------------------------------


    def get_class(self, module_name : typing.AnyStr, class_name : typing.AnyStr) -> typing.Any:
        if not class_name:
            return None

        if module_name:
            m = self.get_module(module_name)
        else:
            m = globals()

        if m == None:
            return None
        
        parts = class_name.split('.')
        try:
            for comp in parts[-1:]:
                m = getattr(m, comp, None)            
            return m
        except AttributeError:
            return None
        
    # -------------------------------------------------------------------------

    
    def prepare(self):
        def load_action_repository() -> typing.Dict[str, typing.Dict] :
            action_repository_path = self._environment.get_action_repository_path()
            
            action_defs : typing.Dict[str, typing.Dict] = {}
    
            sub_dirs = []
            try:
                for o in os.listdir(action_repository_path):
                    if os.path.isdir(os.path.join(action_repository_path,o)) and (self.used_action_names == None or o in self.used_action_names):
                        sub_dirs.append(o)
            except FileNotFoundError as e:
                _LOGGER.error("Action Repository: " + str(e))
            
            for sub_dir in sub_dirs:
                try:
                    with open(os.path.join(action_repository_path, sub_dir, "manifest.json") , 'r') as manifest_file:
                        manifest = json.load(manifest_file)
                        action_defs[sub_dir] = manifest
                except Exception as e:
                    _LOGGER.error(f"Action Manifest {sub_dir}: " + str(e))
                    continue
            
            return action_defs
        
        # -------------------------------------------------------------------------


        def extract_handler(name) -> (str,str):
            if not name:
                return (None,None)

            if name.startswith("buildin."):
                name = ActionManager._buildin_handler_map.get(name)
                

            if name.startswith("."): 
                parts = name[1:].split('.')
                module_name = "." + ".".join(parts[:-1])  
            else:
                parts = name.split('.')
                module_name = ".".join(parts[:-1])  
                
            if len(parts) < 2:
                return (None,None)
            
            return (module_name, parts[-1])
    
        # -------------------------------------------------------------------------


        action_repository = load_action_repository()
        
        for action_name, action_def in action_repository.items():
            handler_module, handler_class = extract_handler(action_def.get("type"))
            cls = self.get_class(handler_module, handler_class)

            action = Action({
                "name" : action_name
            })
            
            if (cls):
                action.handler = cls(
                                    self._environment.create_action_environment(action)
                                )
                action.handler.initialize()

            else:
                action.handler = None

              
            self.actions[action_name] = action 

    # -------------------------------------------------------------------------

    
    def get_action_handler_instance(self, name: str):
        action = self.actions.get(name)
        if action:
            return action.handler
        else:
            return None 
         