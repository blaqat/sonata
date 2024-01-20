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

chat = openai.ChatCompletion

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


def ai(client=None, setup=Callable, default=False, **kwargs):
    def decorator(func):
        name = func.__name__
        new_ai = AI_Type(client, func, **kwargs)
        if setup is not None:
            new_ai.init = setup
            new_ai.can_start = True

        AI_TYPES[name] = new_ai
        if default:
            AI_TYPES["default"] = new_ai
        return new_ai

    return decorator


@ai(client=openai.ChatCompletion, default=True, setup=lambda key: setattr(openai, "api_key", key), model="gpt-3.5-turbo-1106")
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


class PromptManager:
    _config = {"model": None, "max_tokens": None, "temperature": None}

    def setup(self, *args):
        # arg (aitype, key, **kwargs)
        for arg in args:
            _ai = arg[0]
            if isinstance(_ai, str):
                _ai = AI_TYPES.get(_ai, None)
            if _ai is None:
                # Warn user that _ai is not specified
                continue
            if len(arg) > 2 and _ai.can_start:
                _ai.init(arg[1], **arg[2])
            else:
                _ai.init(arg[1])

    def config(self, default_AI=None, key=None, **kwargs):
        # Keeping AI Initialization and default in here until AIManager is created
        AI = default_AI or AI_TYPES["default"]
        if isinstance(AI, str):
            AI = AI_TYPES.get(AI, None)
        self._config = kwargs
        self._config["AI"] = AI
        if key and AI.can_start:
            init_args = self._config.get("init", {})
            AI.init(key, **init_args)

    def __init__(
        self,
        *prompts: Tuple[str, Union[str, Callable]],
        prompt_name: str = None,
        prompt_text: Union[str, callable] = None,
        **kwargs,
    ):
        self.prompts = dict()
        self.config(**kwargs)
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

        config = self._config
        config.update(kwargs)

        return generic_prompt_ai(AI or config.get("AI"), str(prompt), model, config)


# def _get_instructions(prompts: PromptManager = None, instructions=None):
#     instruction_args = None
#     if instructions.isinstance(list):
#         instruction_args = instructions
#         instructions = None
#
#     if instructions.isinstance(tuple):
#         instruction_args = instructions[1:]
#         instructions = instructions[0]
#         instructions = prompts.get(instructions, *instruction_args)
#     elif instructions is None and prompts is not None:
#         instructions = (
#             prompts.get("Instructions", *instruction_args)
#             or prompts.get("SystemInstructions", *instruction_args)
#             or "I am a User you are an AI Assisant, Respond to my messages to aid me"
#         )
#
#     return instructions


# class AIManager:
#     """
#     This class is used to manage communication with the AI model.
#
#     Attributes:
#         prompts (PromptManager): The prompt manager containing the prompts to be used in the conversation.
#         memory (ConversationMemory): The memory object for storing conversation history.
#         memoize (dict): A dictionary for storing key-value pairs in the chatbot memory.
#
#     Methods:
#         reset_memory(): Resets the memory of the AI manager by clearing the conversation prompt messages and chat memory messages.
#         change_instructions(instructions: str): Change the system instructions for the AI chat bot.
#         append_to_instructions(prompt_text: str): Append the given prompt_text to the system instructions for the AI chat bot.
#         update(key: str, func: Callable, *args, **kwargs): Update the value associated with the given key in the ChatBot memory using the provided function.
#         send_chat(message: str) -> dict: Sends a chat message to the AI manager and returns the response.
#         get(key: str, default=None): Retrieve the value associated with the given key from the memoize dictionary.
#         get_human_messages() -> list: Returns a list of human messages from the AI's memory.
#         del_human_messages(): Deletes the most recent human message from the AI's memory.
#         get_ai_messages() -> list: Returns the AI messages from the AI's memory.
#         send_prompt(prompt: str, *prompt_args, max_tokens=None, temperature=None, model=None, **kwargs): Sends a prompt to the AI model for generating a response.
#     """
#
#     # BUG: This function does not work as intended, creates an error when adding memory back.
#     def reset_memory(self):
#         """
#         Resets the memory of the AI manager by clearing the conversation prompt messages and chat memory messages.
#         """
#         self.conversation.prompt.messages = [
#             self.conversation.prompt.messages[0],
#             MessagesPlaceholder(variable_name="memory"),
#             HumanMessagePromptTemplate.from_template("{response}"),
#         ]
#         self.memory.chat_memory.messages = []
#
#     def __init__(
#         self,
#         prompts: PromptManager = None,
#         model=MODEL,
#         open_ai_token=TOKEN,
#         temp=0,
#         max_tokens=1000,
#         instructions=None,
#         verbose=False,
#         streaming: bool = False,
#         handle_token: Callable = None,
#         handle_end: Callable = None,
#         handle_start: Callable = None,
#         summarize: bool = True,
#         **kwargs,
#     ):
#         """
#         Initialize the AI Manager.
#
#         Args:
#             prompts (PromptManager, optional): The prompt manager containing the prompts to be used in the conversation. Defaults to None.
#             model (str, optional): The model to be used for generating responses. Defaults to MODEL.
#             open_ai_token (str, optional): The OpenAI API token. Defaults to TOKEN.
#             temp (float, optional): The temperature value for generating responses. Defaults to 0.
#             max_tokens (int, optional): The maximum number of tokens in the generated response. Defaults to 1000.
#             instructions (str | tuple, optional): The instructions for the conversation. Defaults to None.
#             verbose (bool, optional): Whether to enable verbose mode. Defaults to False.
#             streaming (bool, optional): Whether to enable streaming mode. Defaults to False.
#             handle_token (Callable, optional): Callback function to handle each generated token. Defaults to None.
#             handle_end (Callable, optional): Callback function to handle the end of the conversation. Defaults to None.
#             handle_start (Callable, optional): Callback function to handle the start of the conversation. Defaults to None.
#             summarize (bool, optional): Whether to enable conversation summarization. Defaults to True.
#             **kwargs: Additional keyword arguments.
#
#         Returns:
#             None
#         """
#         instructions = _get_instructions(prompts, instructions)
#
#         handler_class = StreamingStdOutCallbackHandler
#         memory_class = ConversationSummaryMemory
#         if not summarize:
#             memory_class = ConversationBufferMemory
#
#         if (
#             handle_token is not None
#             or handle_end is not None
#             or handle_start is not None
#         ):
#
#             class AIManager_Callback_Handler(BaseCallbackHandler):
#                 __out = True
#
#                 def on_llm_new_token(self, token: str, **kwargs) -> None:
#                     if self.__out:
#                         if handle_token is not None:
#                             handle_token(token)
#                         else:
#                             super().on_llm_new_token(token, **kwargs)
#
#                 def on_llm_start(
#                     self,
#                     serialized: Dict[str, Any],
#                     prompts: List[str],
#                     *,
#                     run_id: UUID,
#                     parent_run_id: UUID | None = None,
#                     tags: List[str] | None = None,
#                     metadata: Dict[str, Any] | None = None,
#                     **kwargs: Any,
#                 ) -> Any:
#                     if (
#                         "Progressively summarize the lines of conversation provided"
#                         in prompts[0]
#                     ):
#                         self.__out = False
#                     else:
#                         self.__out = True
#                         if handle_start is not None:
#                             handle_start()
#                         else:
#                             super().on_llm_start(
#                                 serialized,
#                                 prompts,
#                                 run_id=run_id,
#                                 parent_run_id=parent_run_id,
#                                 tags=tags,
#                                 metadata=metadata,
#                                 **kwargs,
#                             )
#
#                 def on_llm_end(
#                     self,
#                     response: LLMResult,
#                     *,
#                     run_id: UUID,
#                     parent_run_id: UUID | None = None,
#                     **kwargs: Any,
#                 ) -> Any:
#                     if handle_end is not None:
#                         handle_end(response.generations[0][0].message.content)
#                         #    finish_reason=response.generations[0][0].generation_info['finish_reason'])
#                     else:
#                         super().on_llm_end(
#                             response,
#                             run_id=run_id,
#                             parent_run_id=parent_run_id,
#                             **kwargs,
#                         )
#
#             handler_class = AIManager_Callback_Handler
#
#         callbacks = None
#         if streaming:
#             callbacks = [handler_class()]
#
#         llm = ChatOpenAI(
#             openai_api_key=open_ai_token,
#             temperature=temp,
#             max_tokens=max_tokens,
#             model=model,
#             streaming=streaming,
#             callbacks=callbacks,
#         )
#
#         template = ChatPromptTemplate(
#             messages=[
#                 SystemMessagePromptTemplate.from_template(instructions),
#                 # The `variable_name` here is what must align with memory
#                 MessagesPlaceholder(variable_name="memory"),
#                 HumanMessagePromptTemplate.from_template("{response}"),
#             ]
#         )
#
#         self.prompts = prompts or PromptManager()
#         self._max_tokens = max_tokens
#         self._temperature = temp
#         self._model = model
#         self.memory = memory_class(memory_key="memory", return_messages=True, llm=llm)
#         self.memoize = {}
#         if kwargs is not None:
#             for key, value in kwargs.items():
#                 self.memoize[key] = value
#
#         self.conversation = LLMChain(
#             llm=llm, prompt=template, verbose=verbose, memory=self.memory
#         )
#
#     def change_instructions(self, instructions):
#         """
#         Change the system instructions for the AI chat bot.
#
#         Args:
#             instructions (str): The new instructions for the AI chat bot.
#
#         Returns:
#             None
#         """
#         instructions = _get_instructions(
#             prompts=self.prompts, instructions=instructions
#         )
#         self.conversation.prompt.messages[
#             0
#         ] = SystemMessagePromptTemplate.from_template(instructions)
#
#     def append_to_instructions(self, prompt_text: str):
#         """
#         This function appends the given prompt_text to the system instructions for the AI chat bot.
#
#         Parameters:
#             prompt_text (str): The text to be appended to the system instructions.
#
#         Returns:
#             None
#         """
#         self.conversation.prompt.messages[0].prompt.template += prompt_text
#
#     def update(self, key: str, func: Callable, *args, **kwargs):
#         """
#         Update the value associated with the given key in the ChatBot memory using the provided function.
#
#         Parameters:
#             key (str): The key to identify the value in the ChatBot memory.
#             func (Callable): The function to apply on the value.
#             *args: Variable length argument list to be passed to the function.
#             **kwargs: Arbitrary keyword arguments to be passed to the function.
#
#         Raises:
#             KeyError: If the key is not found in the ChatBot memory.
#
#         Returns:
#             None
#         """
#         if key not in self.memoize:
#             raise KeyError(f"Key {key} not found in ChatBot memory")
#         else:
#             self.memoize[key] = func(self.memoize[key], *args, **kwargs)
#
#     def send_chat(self, message: str):
#         """
#         Sends a chat message to the AI manager and returns the response.
#
#         Args:
#             message (str): The message to be sent.
#
#         Returns:
#             dict: The response from the AI manager.
#         """
#         return self.conversation({"response": message})
#
#     def get(self, key: str, default=None):
#         """
#         Retrieve the value associated with the given key from the memoize dictionary.
#
#         If the key is found, return the corresponding value. If the key is not found,
#         return the default value provided.
#
#         Args:
#             key (str): The key to retrieve the value for.
#             default: The value to return if the key is not found. Defaults to None.
#
#         Returns:
#             The value associated with the key if found, otherwise the default value.
#         """
#         return self.memoize[key] or default
#
#     def get_human_messages(self):
#         """
#         Returns a list of human messages from the AI's memory.
#
#         This function retrieves all the messages stored in the AI's memory and filters out
#         only the messages sent by humans. It returns a list of the content of those messages.
#
#         Returns:
#             list: A list of human messages from the AI's memory.
#         """
#         return [
#             message.content
#             for message in self.memory.chat_memory.messages
#             if isinstance(message, HumanMessage)
#         ]
#
#     def del_human_messages(self):
#         """
#         Deletes the most recent human message from the AI's memory.
#
#         This function removes the most recent human message from the AI's memory by filtering out all the messages that are instances of the `HumanMessage` class.
#
#         Parameters:
#             self (AI_manager): The AI_manager instance.
#
#         Returns:
#             None
#         """
#         self.memory.chat_memory.messages = [
#             message
#             for message in self.memory.chat_memory.messages
#             if not isinstance(message, HumanMessage) and "CHAT:" not in message.content
#         ]
#
#     def get_ai_messages(self):
#         """
#         Returns the AI messages from the AI's memory.
#
#         Returns:
#             list: A list of AI messages from the AI's memory.
#         """
#         return [
#             message.content
#             for message in self.memory.chat_memory.messages
#             if isinstance(message, AIMessage)
#         ]
#
#     def send_prompt(
#         self,
#         prompt: str,
#         *prompt_args,
#         max_tokens=None,
#         temperature=None,
#         model=None,
#         **kwargs,
#     ):
#         """
#         Sends a prompt to the AI model for generating a response.
#
#         Args:
#             prompt (str): The prompt to send to the AI model.
#             prompt_args: Additional arguments to be passed to the prompt.
#             max_tokens (int, optional): The maximum number of tokens to generate in the response. Defaults to None.
#             temperature (float, optional): The temperature value for controlling the randomness of the generated response. Defaults to None.
#             model (str, optional): The name of the AI model to use for generating the response. Defaults to None.
#             **kwargs: Additional keyword arguments to be passed to the prompt.
#
#         Returns:
#             str: The generated response from the AI model.
#         """
#         return self.prompts.send(
#             prompt,
#             *prompt_args,
#             max_tokens=max_tokens or self._max_tokens,
#             temperature=temperature or self._temperature,
#             model=model or self._model,
#             **kwargs,
#         )
#
#     def stream_prompt(
#         self,
#         prompt: str,
#         *prompt_args,
#         max_tokens=None,
#         temperature=None,
#         model=None,
#         **kwargs,
#     ):
#         """
#         Streams a prompt to the AI model and returns the generated response.
#
#         Args:
#             prompt (str): The prompt to be sent to the AI model.
#             prompt_args: Additional arguments to be passed to the prompt.
#             max_tokens (int, optional): The maximum number of tokens in the generated response. Defaults to None.
#             temperature (float, optional): The temperature value for controlling the randomness of the generated response. Defaults to None.
#             model (str, optional): The specific model to be used for generating the response. Defaults to None.
#             **kwargs: Additional keyword arguments to be passed to the prompt.
#
#         Returns:
#             str: The generated response from the AI model.
#         """
#         return self.prompts.stream(
#             prompt,
#             *prompt_args,
#             max_tokens=max_tokens or self._max_tokens,
#             temperature=temperature or self._temperature,
#             model=model or self._model,
#             **kwargs,
#         )
