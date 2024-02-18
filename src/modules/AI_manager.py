"""
This module provides functionality for managing AI prompts and generating AI-generated responses.

The module includes the following classes and functions:

- count_tokens(prompt): Counts the number of tokens in a given prompt.
- _get_finish_reason(choice, model): Gets the finish reason for a given choice based on the model.
- generic_prompt_ai_stream(prompt_text, model=MODEL, max_tokens=1250, temperature=0, **kwargs): Generates AI-generated responses in a streaming manner.
- gemeric_ai_prompt(prompt_text, model=MODEL, max_tokens=1250, temperature=0, **kwargs): Uses the OpenAI GPT-4 API to generate a response to the given prompt text.
- PromptManager: A class used to manage prompts.

The PromptManager class provides the following methods:
- __init__(*prompts: Tuple[str, Union[str, Callable]], prompt_name: str = None, prompt_text: Union[str, callable] = None): Initializes the PromptManager object.
- add_prompts(*prompt_text: Tuple[str, Union[str, Callable]]): Adds prompts to the PromptManager object.
- add(prompt_name: str, prompt: Union[str, callable]): Adds a prompt to the PromptManager object.
- get(prompt_name: str, *prompt_args): Retrieves a prompt from the PromptManager object.
- add_prompts_from(prompt_manager): Adds prompts from another PromptManager object, a dictionary, a list, or a tuple to the current PromptManager.
- send(prompt: str, *prompt_args, model=MODEL, max_tokens=1250, temperature=0, **kwargs): Sends a prompt to the AI model and returns the generated response.
- stream(prompt: str, *prompt_args, model=MODEL, max_tokens=1250, temperature=0, **kwargs): Generates a stream of AI-generated text based on the given prompt.
"""

from os import close
from typing import Any, Callable, Dict, List, Tuple, Union
import copy

from discord.ext.commands import core, errors
from modules.utils import setter


AI_TYPES = {"default": None}


class AI_Type:
    can_start = False

    def __init__(self, client, predicate, **kwargs):
        self.client = client
        self.func = predicate
        self.config = {}
        if kwargs is not None:
            for key, value in kwargs.items():
                self.config[key] = value

    def setup(self, *args):
        # print(self, *args)
        if self.can_start:
            self.init(self, *args)

    @classmethod
    def initalize(cfg, *args):
        # arg (aitype, key, **kwargs)
        for arg in args:
            _ai = arg[0]
            if isinstance(_ai, str):
                _ai = AI_TYPES.get(_ai, None)
            if _ai is None:
                # Warn user that _ai is not specified
                continue
            if len(arg) > 2 and _ai.can_start:
                _ai.setup(arg[1], **arg[2])
            else:
                _ai.setup(arg[1])


class AI_Error(Exception):
    pass


def gemeric_ai_prompt(ai_type: AI_Type | str, prompt_text, model=None, config={}):
    if isinstance(ai_type, str):
        ai_type = AI_TYPES.get(ai_type, None)
    ai_type = ai_type or AI_TYPES["default"]
    ai_config = ai_type.config
    config.update(ai_config)
    model = model or config.get("model", None)
    if model is None:
        raise AI_Error("No model specified")
    return ai_type.func(ai_type.client, prompt_text, model, config)


class PromptManager:
    def __init__(
        self,
        *prompts: Tuple[str, Union[str, Callable]],
        prompt_name: str = None,
        prompt_text: Union[str, callable] = None,
    ):
        self.prompts = dict()
        if prompt_name is not None and prompt_text is not None:
            self.add(prompt_name, prompt_text)
        if prompts is not None:
            self.add_prompts(*prompts)

    def add_prompts(self, *prompt_text: Tuple[str, Union[str, Callable]]):
        for prompt_name, prompt in prompt_text:
            self.add(prompt_name, prompt)

    def add(self, prompt_name: str, prompt: Union[str, callable]):
        self.prompts[prompt_name] = prompt

    def get(self, prompt_name: str, *prompt_args):
        if prompt_name not in self.prompts:
            return None
        if callable(self.prompts[prompt_name]):
            return self.prompts[prompt_name](*prompt_args)
        else:
            return self.prompts[prompt_name]

    def exists(self, prompt_name: str):
        return prompt_name in self.prompts

    def add_prompts_from(self, prompt_manager):
        if isinstance(prompt_manager, PromptManager):
            self.prompts.update(prompt_manager.prompts)
        elif isinstance(prompt_manager, dict):
            self.prompts.update(prompt_manager)
        elif isinstance(prompt_manager, list):
            self.add_prompts(*prompt_manager)
        elif isinstance(prompt_manager, tuple):
            self.add(*prompt_manager)
        else:
            raise TypeError(
                f"Cannot add prompts from object of type {type(prompt_manager)}"
            )

    def send(self, prompt, *prompt_args, model=None, AI=None, config={}):
        if prompt in self.prompts:
            prompt = self.get(prompt, *prompt_args)

        return gemeric_ai_prompt(AI, str(prompt), model, config)


def _config_builder(aiman):
    self = aiman

    class Config:
        def get(kelf, name: str, *default_to):
            _c = self.get("config")
            if name in _c:
                return _c[name]
            else:
                for d in default_to:
                    if d is not None:
                        return d
            return None

        def set(kelf, **kwargs):
            self.update("config", **kwargs)

        def merge(kelf, *configs):
            self.update("config", *configs)

        def setup(kelf):
            _setup = kelf.get("setup")
            AI_Type.initalize(tuple([*_setup]))

    return Config


class AI_Manager:
    lazy = False
    sub_classes = {}
    on_load = []

    def __getattribute__(self, __name: str) -> Any:
        sub = super().__getattribute__("sub_classes")
        if __name in sub:
            sc = sub[__name]
            # Build the class if it is a callable
            if isinstance(sc, Callable) and not isinstance(sc, type):
                sc = sc(self)()
                sub[__name] = sc
            return sc
        return super().__getattribute__(__name)

    class M:  # Higher order function alternatives
        _a = None
        _p = None
        m = None

        @classmethod
        def cls(cls, class_name, class_body):
            cls._a.sub_classes[class_name] = class_body

        @classmethod
        def builder(cls, func):
            cls.cls(func.__name__, func)

            return func

        @classmethod
        def do(cls, *args, **kwargs):
            return cls._a.do(*args, **kwargs)

        @classmethod
        def get(cls, *args, **kwargs):
            return cls._a.get(*args, **kwargs)

        @classmethod
        def set(cls, *args, **kwargs):
            return cls._a.set(*args, **kwargs)

        @classmethod
        def update(cls, *args, **kwargs):
            return cls._a.update(*args, **kwargs)

        @classmethod
        def reset(cls, *args, **kwargs):
            return cls._a.reset(*args, **kwargs)

        @classmethod
        def add(cls, *args, **kwargs):
            return cls._a.add(*args, **kwargs)

        @classmethod
        def forget(cls, *args, **kwargs):
            return cls._a.forget(*args, **kwargs)

        @classmethod
        def remember(cls, *args, **kwargs):
            return cls._a.remember(*args, **kwargs)

        @classmethod
        def init(cls, aim):
            cls._a = aim
            cls._p = aim.prompt_manager
            cls.m = aim.memory

        @classmethod
        def ai(cls, client=None, setup=Callable, default=False, **kwargs):
            def decorator(func):
                name = func.__name__
                # print(client, func, kwargs)
                new_ai = AI_Type(client, func, **kwargs)
                if setup is not None:
                    new_ai.init = setup
                    new_ai.can_start = True
                    AI_TYPES[name] = new_ai
                if default:
                    AI_TYPES["default"] = new_ai
                    return new_ai

            return decorator

        @classmethod
        def prompt(cls, func, prompt_name=None):
            if prompt_name is None:
                prompt_name = func.__name__
            cls._p.add(prompt_name, func)
            return func

        @classmethod
        def effect(cls, key, event_name=None, prepend=True):
            def decorator(hook_func):
                nonlocal key, event_name, prepend
                if cls._a.lazy:

                    def lazy():
                        cls._a.effect(key, event_name, hook_func, prepend)
                        return hook_func

                    cls._a.on_load.append(lazy)
                else:
                    cls._a.effect(key, event_name, hook_func, prepend)
                return hook_func

            if not event_name:
                # Function name should be "key_eventname"
                name = key.__name__.split("_")
                event_name, k = name[0], name[1]
                if cls._a.lazy:

                    def lazy():
                        cls._a.effect(k, event_name, key, prepend)
                        return key

                    cls._a.on_load.append(lazy)
                    return lazy
                cls._a.effect(k, event_name, key)
                return key

            return decorator

        @classmethod
        def effect_post(cls, key, event_name=None, prepend=False):
            def decorator(hook_func):
                nonlocal key, event_name, prepend
                if cls._a.lazy:

                    def lazy():
                        cls._a.effect(key, event_name, hook_func, prepend)
                        return hook_func

                    cls._a.on_load.append(lazy)
                    return lazy

                cls._a.effect(key, event_name, hook_func, prepend)
                return hook_func

            if not event_name:
                name = key.__name__.split("_")
                event_name, k = name[0], name[1]
                if cls._a.lazy:

                    def lazy():
                        cls._a.effect(k, event_name, key, prepend)
                        return key

                    cls._a.on_load.append(lazy)
                    return lazy
                cls._a.effect(k, event_name, key, prepend)
                return key

            return decorator

        @classmethod
        def event(cls, key, event_name=None):
            def decorator(func):
                nonlocal key, event_name
                cls._a.add(key, event_name, func)
                return func

            if not event_name:
                # Function name should be "key_eventname"
                name = key.__name__.split("_")
                event_name, k = name[0], name[1]
                cls._a.add(k, event_name, key)
                return key

            return decorator

        @classmethod
        def mem(cls, v, key=None, inner=False, u=None, s=None, r=None, **kwargs):
            def decorator(func):
                nonlocal key, v, inner, u, s, r
                event_name = func.__name__

                if key is None:
                    split = event_name.split("_")
                    event_name, key = split[0], split[1]

                if inner is True:
                    split = event_name.split("_")
                    event_name, inner = split[0], split[1]

                cls._a.remember(
                    key,
                    v,
                    update_func=func if event_name == "update" else u,
                    set_func=func if event_name == "set" or event_name == "add" else s,
                    reset_func=func if event_name == "reset" else r,
                    inner=inner,
                    **kwargs,
                )

                if event_name not in ["update", "set", "reset", "add"]:
                    cls._a.add(key, event_name, func)

                return func

            return decorator

    @classmethod
    def init(cls, *args, lazy=False, config={}, **kwargs):
        if lazy:
            l = cls(PromptManager(), *args, **kwargs, name="LAZY")
            l.plugin_config = config
            return l, l.M, l.prompt_manager
        t = cls(*args, **kwargs)
        return t, t.M

    def __init__(
        self,
        prompt_manager,
        default_AI=None,
        default_args: str | tuple = tuple(),
        memoi: dict = dict(),
        name="AI",
        **config,
    ):
        if name == "LAZY":
            self.on_load = []
            self.lazy = True
        else:
            self.lazy = False
        self.sub_classes = {}
        self.name = name
        Config = _config_builder(self)

        self.config = Config()
        self.__init_memoi(memoi)

        if (
            not self.lazy
            and not prompt_manager.exists("Instructions")
            and not prompt_manager.exists("SystemInstructions")
        ):
            prompt_manager.add(
                "Instructions",
                lambda _,
                message,
                nick: f"I am a User you are an AI Assisant, Respond to my messages to aid me. My message: {message}",
            )

        self.prompt_manager: PromptManager = prompt_manager

        self.M.init(self)

        def update_config(M, *merge, **kvpairs):
            M["value"].update(*merge)
            for key, value in kvpairs.items():
                M["value"][key] = value
            return M["value"]

        def set_config(M, key, value):
            M["value"][key] = value

        self.add("config", "update", update_config, ignore_lazy=True)
        self.add("config", "set", set_config, ignore_lazy=True)
        self.config.merge(config)
        self.config.set(AI=default_AI, setup=default_args, **config)

    def extend(A, Plugins, **configs):
        for LM in Plugins:
            L = None
            try:
                L = LM.L
            except AttributeError:
                print(f"Could not extend {A.name} with {LM}")
                continue

            # print("DOING ", LM.__plugin_name__)

            for key, value in L.memory.items():
                if "lazy" in value:
                    check_for = value["lazy"]
                    if key in A.memory:
                        for k in check_for:
                            A.memory[key][k] = value[k]
                    else:
                        A.memory[key] = value
                        if not A.lazy:
                            del A.memory[key]["lazy"]

            for class_name, class_body in L.sub_classes.items():
                if class_name not in A.sub_classes:
                    if isinstance(class_body, Callable) and not isinstance(
                        class_body, type
                    ):
                        class_body = class_body(A)()
                    A.sub_classes[class_name] = class_body

            for func in L.on_load:
                func()
            # print(
            #     LM.__plugin_name__, L.plugin_config, configs.get(LM.__plugin_name__, {})
            # )
            plugin_config = copy.deepcopy(L.plugin_config)
            plugin_config.update(configs.get(LM.__plugin_name__, {}))
            # print(plugin_config)
            A.config.merge(plugin_config)
            A.prompt_manager.add_prompts_from(L.prompt_manager)
            L.prompt_manager = A.prompt_manager

            del L

    def __init_memoi(self, memoi):
        # memoi["chat"] = dict()
        memoi["config"] = dict()
        self.memory = dict()
        for key, value in memoi.items():
            self.remember(key, value, ignore_lazy=True)

    def __default_update(self, _, new_value):
        return new_value

    def __default_set(self, M, new_value):
        M["value"] = new_value

    def __default_reset(self, M):
        M["value"] = copy.deepcopy(M["default_value"])

    def remember(
        self,
        key,
        value,
        default_value=None,
        update_func=None,
        set_func=None,
        reset_func=None,
        inner=False,
        ignore_lazy=False,
        **kwargs,
    ):
        if inner:
            m = self.memory.get(key)
            if not m:
                raise KeyError(f"Key {key} not found in {self.name}'s memory")
            m[inner] = value
            if self.lazy and not ignore_lazy:
                if "lazy" not in m:
                    m["lazy"] = set()
                m["lazy"].add(inner)
            for e, f in kwargs.items():
                self.add(key, e, f)
            return

        self.memory[key] = {
            "default_value": value if default_value is None else default_value,
            "value": copy.deepcopy(value),
            "update": update_func or self.__default_update,
            "set": set_func or self.__default_set,
            "reset": reset_func or self.__default_reset,
        }

        if self.lazy and not ignore_lazy:
            self.memory[key]["lazy"] = set()
        for e, f in kwargs.items():
            self.add(key, e, f)

    def add(self, key, event_name, event_func, ignore_lazy=False, **kwargs):
        if key in self.memory:
            if self.lazy and not ignore_lazy:
                if "lazy" not in self.memory[key]:
                    self.memory[key]["lazy"] = set()
                self.memory[key]["lazy"].add(event_name)
            self.memory[key][event_name] = event_func

        for e, f in kwargs.items():
            self.add(key, e, f)

    def do(self, key, event_name, *args, **kwargs):
        if key in self.memory:
            if callable(self.memory[key][event_name]):
                return self.memory[key][event_name](self.memory[key], *args, **kwargs)
            else:
                passed_args = args
                for func in self.memory[key][event_name]:
                    passed_args = func(self.memory[key], *passed_args, **kwargs)
                return passed_args

    def forget(self, key):
        del self.memory[key]

    def update(self, key, *args, **kwargs):
        if key in self.memory:
            self.memory[key]["value"] = self.do(key, "update", *args, **kwargs)

    def set(self, key, *args, inner=False, **kwargs):
        if key in self.memory:
            if inner:
                self.memory[key][inner] = args[0]
                return
            return self.do(key, "set", *args, **kwargs)

    def get(self, key, val="value", inner=True, default=None):
        if not inner:
            return self.memory.get(key, default)
        if not key in self.memory:
            print(f"Key {key} not found in ChatBot memory")
            return default

        if not val in self.memory[key]:
            print(f"Key {val} not found in ChatBot memory[{key}]")
            return default

        return self.memory[key].get(val, default)

    def reset(self, key, *args, **kwargs):
        if key in self.memory:
            self.memory[key]["value"] = self.do(key, "reset", *args, **kwargs)

    # def effect(self, key, event_name, hook_func, prepend=True):
    #     if key not in self.memory:
    #         return
    #
    #     current = self.memory[key][event_name]
    #     if callable(current):
    #         current = [current]
    #
    #     if prepend:
    #         current.insert(0, hook_func)
    #     else:
    #         current.append(hook_func)
    #
    #     self.add(key, event_name, current)

    def effect(self, key, event_name, hook_func, prepend=True):
        if key not in self.memory:
            return

        hooked_over = self.memory[key][event_name]
        new_function = None

        if prepend:

            def new_function_pre(M, *args, **kwargs):
                nonlocal hook_func, key
                if isinstance(hook_func, str):
                    hook_func = self.memory[key][hook_func]
                args = hook_func(M, *args, **kwargs)
                return hooked_over(M, *args, **kwargs)

            new_function = new_function_pre
        else:

            def new_function_post(M, *args, **kwargs):
                nonlocal hook_func, key
                if isinstance(hook_func, str):
                    hook_func = self.memory[key][hook_func]
                args = hooked_over(M, *args, **kwargs)
                if isinstance(args, tuple) or isinstance(args, list):
                    return hook_func(M, *args, **kwargs)
                return hook_func(M, args, **kwargs)

            new_function = new_function_post

        self.add(key, event_name, new_function)
