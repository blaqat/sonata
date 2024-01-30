"""
This module provides functionality for managing AI prompts and generating AI-generated responses.

The module includes the following classes and functions:

- count_tokens(prompt): Counts the number of tokens in a given prompt.
- _get_finish_reason(choice, model): Gets the finish reason for a given choice based on the model.
- generic_prompt_ai_stream(prompt_text, model=MODEL, max_tokens=1250, temperature=0, **kwargs): Generates AI-generated responses in a streaming manner.
- generic_prompt_ai(prompt_text, model=MODEL, max_tokens=1250, temperature=0, **kwargs): Uses the OpenAI GPT-4 API to generate a response to the given prompt text.
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

from typing import Any, Callable, Dict, List, Tuple, Union
import openai
import copy

chat = openai.ChatCompletion

AI_TYPES = {"default": None}
# TODO: General Clean Up and Renaming Classes


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
        print(self, *args)
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


class AIError(Exception):
    pass


def ai(client=None, setup=Callable, default=False, **kwargs):
    def decorator(func):
        name = func.__name__
        print(client, func, kwargs)
        new_ai = AI_Type(client, func, **kwargs)
        if setup is not None:
            new_ai.init = setup
            new_ai.can_start = True

        AI_TYPES[name] = new_ai
        if default:
            AI_TYPES["default"] = new_ai
        return new_ai

    return decorator


@ai(
    client=openai.ChatCompletion,
    default=True,
    setup=lambda _, key: setattr(openai, "api_key", key),
    model="gpt-3.5-turbo-1106",
)
def OpenAI(client, prompt, model, config):
    return (
        client.create(
            model=model,
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            max_tokens=config.get("max_tokens", 1250),
            temperature=config.get("temp") or config.get("temperature") or 0,
        )
        .choices[0]
        .message.content
    )


def generic_prompt_ai(ai_type: AI_Type | str, prompt_text, model=None, config={}):
    if isinstance(ai_type, str):
        ai_type = AI_TYPES.get(ai_type, None)
    ai_type = ai_type or AI_TYPES["default"]
    ai_config = ai_type.config
    config.update(ai_config)
    model = model or config.get("model", None)
    if model is None:
        # Warn user that model is not specified
        pass
    return ai_type.func(ai_type.client, prompt_text, model, config)


# TODO: Add system for @higher-order function decotrators for
# AI_Type, effects, stored memory, and prompt_manager
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

    def send(self, prompt, *prompt_args, model=None, AI=None, **kwargs):
        if prompt in self.prompts:
            prompt = self.get(prompt, *prompt_args)

        return generic_prompt_ai(AI, str(prompt), model, kwargs)


def _config_builder(AIManager):
    self = AIManager

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
            print(_setup, self.get("config"))
            AI_Type.initalize(tuple([*_setup]))

    return Config


def _chat_builder(aiman, prompt_manager):
    self = aiman

    class Chat:
        max_chats = 50

        def get_chat(kelf, id):
            chat = self.get("chat")
            if chat.get(id) is None:
                chat[id] = []
            return chat[id]

        def send(
            kelf,
            id,
            message_type,
            author,
            message,
        ):
            chat = kelf.get_chat(id)
            self.set("chat", id, message_type, author, message)
            # chat.append((message_type, author, message))
            if len(chat) > kelf.max_chats and self.config.get("summarize"):
                summmary = self.do("chat", "summarize", id)
                kelf.delete()
                kelf.send(id, "System", "PreviousChatSummary", summmary)

        def request(
            kelf,
            id,
            message: str,
            *args,
            AI=self.config.get("AI"),
            error_prompt=None,
            **config,
        ):
            try:
                prompt = prompt_manager.get(
                    "Instructions", kelf.get_history(id), message, *args
                )

                response = prompt_manager.send(
                    prompt, kelf.get_history(id), message, *args, AI=AI, **config
                )

                # response = "AAAAAAAAAAAAAAAAAA"
            except Exception as e:
                if error_prompt is not None:
                    response = prompt_manager.send(error_prompt(e), AI=AI, **config)
                else:
                    response = f"Response failed: {e}"
            finally:
                kelf.send(id, "Bot", self.name, response)
                return response

        def get_history(
            kelf,
            chat_id,
            human_messages=None,
            ai_messages=None,
            system_messages=None,
        ):
            if (
                human_messages is None
                and ai_messages is None
                and system_messages is None
            ):
                return kelf.get_chat(chat_id)
            else:
                # human_messages: User, ai_messages: Bot, system_messages: System
                return [
                    m
                    for m in kelf.get_chat(chat_id)
                    if m[0]
                    in [
                        human_messages and "User",
                        ai_messages and "Bot",
                        system_messages and "System",
                    ]
                ]

        def delete(
            kelf,
            chat_id,
            human_messages=True,
            ai_messages=True,
            system_messages=True,
        ):
            if (
                human_messages is True
                and ai_messages is True
                and system_messages is True
            ):
                self.reset("chat", chat_id)
            else:
                # human_messages: User, ai_messages: Bot, system_messages: System
                self.get("chat")[chat_id] = kelf.get_history(
                    chat_id, human_messages, ai_messages, system_messages
                )

    return Chat


class AIManager:
    def __init__(
        self,
        prompt_manager,
        default_AI=None,
        default_args: str | tuple = tuple(),
        summarize_chat: bool = True,
        memoi: dict = dict(),
        name="AI",
        **config,
    ):
        self.name = name
        Config = _config_builder(self)

        self.config = Config()
        self.__init_memoi(memoi)

        Chat = _chat_builder(self, prompt_manager)
        has_instructions = prompt_manager.exists(
            "Instructions"
        ) or prompt_manager.exists("SystemInstructions")
        if has_instructions is not True:
            prompt_manager.add(
                "Instructions",
                lambda history,
                message,
                nick: f"I am a User you are an AI Assisant, Respond to my messages to aid me. My message: {message}",
            )

        if not prompt_manager.exists("SummarizeChat"):
            prompt_manager.add(
                "SummarizeChat", lambda chat_log: "Summarize the chatlog: " + chat_log
            )

        self.prompt_manager = prompt_manager

        self.chat = Chat()

        self.add(
            "chat",
            "summarize",
            lambda M, id: self.prompt_manager.send(
                "SummarizeChat",
                M["value"][id],
                AI=self.config.get("AI"),
                **self.memory["config"],
            ),
        )

        self.add(
            "chat",
            "reset",
            lambda M, chat_id: setattr(
                M["value"][chat_id], copy.deepcopy(M["default_value"])
            ),
        )

        self.add(
            "chat",
            "set",
            lambda M, chat_id, message_type, author, message: M["value"][
                chat_id
            ].append((message_type, author, message)),
        )

        def update_config(M, *merge, **kvpairs):
            M["value"].update(*merge)
            for key, value in kvpairs.items():
                M["value"][key] = value
            return M["value"]

        def set_config(M, key, value):
            M["value"][key] = value

        self.add("config", "update", update_config)
        self.add("config", "set", set_config)
        # self.memory["config"]["summarize"] = summarize_chat
        self.set("config", "summarize", summarize_chat)
        self.config.merge(config)
        self.config.set(AI=default_AI, setup=default_args, **config)
        print(self.memory["config"])
        self.config.setup()

    def __init_memoi(self, memoi):
        memoi["chat"] = dict()
        memoi["config"] = dict()
        self.memory = dict()
        for key, value in memoi.items():
            self.remember(key, value)

    def __default_update(self, M, new_value, *args, **kwargs):
        return new_value

    def __default_set(self, M, new_value, *args, **kwargs):
        M["value"] = new_value

    def __default_reset(self, M, *args, **kwargs):
        M["value"] = copy.deepcopy(M["default_value"])

    def remember(
        self,
        key,
        default_value,
        update_func=None,
        set_func=None,
        reset_func=None,
        inner=False,
    ):
        if inner:
            m = self.memory.get(key)
            if not m:
                raise KeyError(f"Key {key} not found in ChatBot memory")
            m[inner] = default_value
            return

        self.memory[key] = {
            "default_value": default_value,
            "value": copy.deepcopy(default_value),
            "update": update_func or self.__default_update,
            "set": set_func or self.__default_set,
            "reset": reset_func or self.__default_reset,
        }

    def add(self, key, event_name, event_func):
        if key in self.memory:
            self.memory[key][event_name] = event_func

    def do(self, key, event_name, *args, **kwargs):
        if key in self.memory:
            return self.memory[key][event_name](self.memory[key], *args, **kwargs)

    def forget(self, key):
        del self.memory[key]

    def update(self, key, *args, **kwargs):
        if key in self.memory:
            self.memory[key]["value"] = self.memory[key]["update"](
                self.memory[key], *args, **kwargs
            )

    def set(self, key, *args, inner=False, **kwargs):
        if key in self.memory:
            if inner:
                self.memory[key][inner] = args[0]
                return
            self.memory[key]["set"](self.memory[key], *args, **kwargs)

    def get(self, key, val="value", default=None):
        if not key in self.memory:
            print(f"Key {key} not found in ChatBot memory")
            return default

        if not val in self.memory[key]:
            print(f"Key {val} not found in ChatBot memory[{key}]")
            return default

        return self.memory[key].get(val, default)

    def reset(self, key, *args, **kwargs):
        if key in self.memory:
            self.memory[key]["value"] = self.memory[key]["reset"](
                self.memory[key], *args, **kwargs
            )

    def effect(self, key, event_name, hook_func, prepend=True):
        if key not in self.memory:
            return

        hooked_over = self.memory[key][event_name]

        if prepend:

            def new_function(M, *args, **kwargs):
                nonlocal hook_func, key
                if isinstance(hook_func, str):
                    hook_func = self.memory[key][hook_func]
                args = hook_func(M, *args, **kwargs)
                return hooked_over(M, *args, **kwargs)
        else:

            def new_function(M, *args, **kwargs):
                nonlocal hook_func, key
                if isinstance(hook_func, str):
                    hook_func = self.memory[key][hook_func]
                hooked_over(M, *args, **kwargs)
                return hook_func(M, *args, **kwargs)

        self.add(key, event_name, new_function)
