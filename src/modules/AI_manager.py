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

import os
from typing import Any, Dict, List, Union, Tuple, Callable
from uuid import UUID
from langchain.schema.output import LLMResult
import openai
import tiktoken
from dotenv import load_dotenv
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.chains import LLMChain
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationSummaryMemory, ConversationBufferMemory
from langchain.schema.messages import HumanMessage, AIMessage
from langchain.callbacks.streaming_stdout import StreamingStdOutCallbackHandler
from langchain.callbacks.base import BaseCallbackHandler

load_dotenv()
MODEL = os.getenv("DEFAULT_MODEL")
TOKEN = os.getenv("OPENAI_TOKEN")
chat = openai.ChatCompletion


def count_tokens(prompt, model=MODEL):
    """
    Count the number of tokens in a given prompt.

    Parameters:
    prompt (str): The prompt to count tokens from.

    Returns:
    int: The number of tokens in the prompt.
    """
    return len(tiktoken.encoding_for_model(model).encode(prompt))


def _get_finish_reason(choice, model):
    """
    Get the finish reason for a given choice based on the model.

    Args:
        choice (Choice): The choice object.
        model (str): The model name.

    Returns:
        str or None: The finish reason if the model is not "vision", otherwise the finish type or None.
    """
    if "vision" in model:
        return choice.finish_details and choice.finish_details.get('type', None) or None
    else:
        return choice.finish_reason


def generic_prompt_ai_stream(prompt_text, model=MODEL, max_tokens=1250, temperature=0, **kwargs):
    '''
    Generates AI-generated responses in a streaming manner.

    Args:
        prompt_text (str): The text prompt to start the conversation.
        model (str): The AI model to use for generating responses. Default is MODEL.
        max_tokens (int): The maximum number of tokens to generate. Default is 1250.
        temperature (float): The temperature value for controlling the randomness of the generated responses. Default is 0.
        **kwargs: Additional keyword arguments to include in the conversation.

    Returns:
        dict: A dictionary containing the following keys:
            - "prompt_tokens" (int): The number of tokens in the prompt text.
            - "out" (function): A function that handles the AI-generated responses in a streaming manner.

    Example:
        response = generic_prompt_ai_stream("Hello, how are you?")
        out_func = response["out"]
        out_func(print)  # Prints the AI-generated responses to the console.
    '''

    content = [{"type": "text", "text": prompt_text}]

    if kwargs is not None:
        for key, value in kwargs.items():
            content.append({"type": key, key: value})

    response = chat.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        stream=True
    )

    def handle_response(handle_token: Callable, handle_end: Callable = None) -> str:
        for addition in response:
            try:
                finish_reason = _get_finish_reason(addition.choices[0], model)
                if finish_reason is not None:
                    if handle_end is not None:
                        handle_end()
                    return addition.choices[0].finish_reason
                addition = addition.choices[0].delta.get("content", "")
                handle_token(addition or "")
            except:
                return None

    return {
        "prompt_tokens": count_tokens(prompt_text),
        "out": handle_response,
    }


def generic_prompt_ai(prompt_text, model=MODEL, max_tokens=1250, temperature=0, **kwargs):
    """
    Uses the OpenAI GPT-4 API to generate a response to the given prompt text.

    Args:
        prompt_text (str): The text prompt to generate a response to.
        model (str): The ID of the GPT-3 model to use. Defaults to the global MODEL variable.
        max_tokens (int): The maximum number of tokens to generate in the response. Defaults to 1250.
        temperature (float): Controls the "creativity" of the generated response. Higher values result in more creative responses. Defaults to 1.

    Returns:
        dict: A dictionary containing information about the generated response, including the number of tokens in the prompt, the reason the response generation finished, and the generated response text.
    """
    content = [{"type": "text", "text": prompt_text}]

    if kwargs is not None:
        for key, value in kwargs.items():
            content.append({"type": key, key: value})

    response = chat.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": content,
            }
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    return {
        "prompt_tokens": count_tokens(prompt_text, model),
        "finished_reason": _get_finish_reason(response.choices[0], model),
        "response": response.choices[0].message.content,
    }


class PromptManager:
    """
    This class is used to manage prompts.

    Attributes:
        prompts (dict): A dictionary to store prompt names and corresponding prompt texts or callables.

    Methods:
        __init__(self, *prompts: Tuple[str, Union[str, Callable]], prompt_name: str = None, prompt_text: Union[str, callable] = None):
            Initializes the PromptManager object.

        add_prompts(self, *prompt_text: Tuple[str, Union[str, Callable]]):
            Adds prompts to the PromptManager object.

        add(self, prompt_name: str, prompt: Union[str, callable]):
            Adds a prompt to the PromptManager object.

        get(self, prompt_name: str, *prompt_args):
            Retrieves a prompt from the PromptManager object.

        add_prompts_from(self, prompt_manager):
            Adds prompts from another PromptManager object, a dictionary, a list, or a tuple to the current PromptManager.

        send(self, prompt: str, *prompt_args, model=MODEL, max_tokens=1250, temperature=0, **kwargs):
            Sends a prompt to the AI model and returns the generated response.

        stream(self, prompt: str, *prompt_args, model=MODEL, max_tokens=1250, temperature=0, **kwargs):
            Generates a stream of AI-generated text based on the given prompt.
    """
    _config = {'model': None, 'max_tokens': None, 'temperature': None}

    def config(self, model=MODEL, max_tokens=1250, temperature=0, key=None):
        self._config = {'model': model,
                        'max_tokens': max_tokens, 'temperature': temperature}
        if key:
            openai.api_key = key

    def __init__(self, *prompts: Tuple[str, Union[str, Callable]], prompt_name: str = None, prompt_text: Union[str, callable] = None):
        """
        Initializes the PromptManager object.

        Args:
            prompts (Tuple[str, Union[str, Callable]]): Variable number of tuples containing prompt names and corresponding prompt texts or callables.
            prompt_name (str, optional): Name of the prompt to be added. Defaults to None.
            prompt_text (Union[str, callable], optional): Text or callable for the prompt to be added. Defaults to None.
        """
        self.prompts = dict()
        self.config()
        if prompt_name is not None and prompt_text is not None:
            self.add(prompt_name, prompt_text)
        if prompts is not None:
            self.add_prompts(*prompts)

    def add_prompts(self, *prompt_text: Tuple[str, Union[str, Callable]]):
        """
        Adds prompts to the PromptManager object.

        Parameters:
        *prompt_text (Tuple[str, Union[str, Callable]]): Variable-length argument list of tuples containing prompt names and prompts.
            Each tuple should have the following structure: (prompt_name, prompt).
            - prompt_name (str): The name of the prompt.
            - prompt (str or Callable): The prompt text or a callable object that generates the prompt text.

        Returns:
        None
        """
        for prompt_name, prompt in prompt_text:
            self.add(prompt_name, prompt)

    def add(self, prompt_name: str, prompt: Union[str, callable]):
        """
        Adds a prompt to the PromptManager object.

        Parameters:
        prompt_name (str): The name of the prompt.
        prompt (Union[str, callable]): The prompt to be added. It can be a string or a callable object.

        Returns:
        None
        """
        self.prompts[prompt_name] = prompt

    def get(self, prompt_name: str, *prompt_args):
        """
        Retrieves a prompt from the PromptManager object.

        Parameters:
        - prompt_name (str): The name of the prompt to retrieve.
        - prompt_args (tuple): Optional arguments to pass to the prompt function.

        Returns:
        - The prompt value if it exists in the PromptManager object, None otherwise.
        """
        if prompt_name not in self.prompts:
            return None
        if callable(self.prompts[prompt_name]):
            return self.prompts[prompt_name](*prompt_args)
        else:
            return self.prompts[prompt_name]

    def add_prompts_from(self, prompt_manager):
        """
        Adds prompts from another PromptManager object, a dictionary, a list, or a tuple to the current PromptManager.

        Parameters:
        - prompt_manager: Another PromptManager object, a dictionary, a list, or a tuple containing prompts.

        Raises:
        - TypeError: If the prompt_manager is not of type PromptManager, dictionary, list, or tuple.

        Returns:
        - None
        """
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
                f"Cannot add prompts from object of type {type(prompt_manager)}")

    def send(self, prompt: str, *prompt_args, model=None, max_tokens=None, temperature=0, **kwargs):
        """
        Sends a prompt to the AI model and returns the generated response.

        Args:
            prompt (str): The prompt to send to the AI model.
            prompt_args: Additional arguments to format the prompt string.
            model: The AI model to use for generating the response. Defaults to MODEL.
            max_tokens (int): The maximum number of tokens to generate in the response. Defaults to 1250.
            temperature (float): The temperature parameter for controlling the randomness of the generated response. 
                A higher value (e.g., 1.0) produces more random responses, while a lower value (e.g., 0.2) produces 
                more deterministic responses. Defaults to 0.
            **kwargs: Additional keyword arguments to pass to the AI model.

        Returns:
            str: The generated response from the AI model.
        """
        if prompt in self.prompts:
            prompt = self.get(prompt, *prompt_args)

        config = self._config

        return generic_prompt_ai(str(prompt), max_tokens=max_tokens or config['max_tokens'], temperature=temperature or config['temperature'], model=model or config['model'], **kwargs)

    def stream(self, prompt: str, *prompt_args, model=MODEL, max_tokens=1250, temperature=0, **kwargs):
        """
        Generates a stream of AI-generated text based on the given prompt.

        Args:
            prompt (str): The initial prompt for generating the text.
            *prompt_args: Additional arguments to be passed to the prompt.
            model (optional): The AI model to be used for generating the text. Defaults to MODEL.
            max_tokens (int, optional): The maximum number of tokens to generate. Defaults to 1250.
            temperature (int, optional): The randomness of the generated text. Defaults to 0.
            **kwargs: Additional keyword arguments to be passed to the AI model.

        Returns:
            str: The generated AI-generated text.
        """
        if prompt in self.prompts:
            prompt = self.get(prompt, *prompt_args)

        return generic_prompt_ai_stream(str(prompt), max_tokens=max_tokens, temperature=temperature, model=model, **kwargs)


def _get_instructions(prompts: PromptManager = None, instructions=None):
    """
    Get the instructions for the AI assistant.

    Args:
        prompts (PromptManager, optional): The prompt manager object. Defaults to None.
        instructions (list or tuple or None, optional): The instructions to retrieve. Defaults to None.

    Returns:
        str: The instructions for the AI assistant.
    """

    instruction_args = None
    if type(instructions) == list:
        instruction_args = instructions
        instructions = None

    if type(instructions) == tuple:
        instruction_args = instructions[1:]
        instructions = instructions[0]
        instructions = prompts.get(instructions, *instruction_args)
    elif instructions is None and prompts is not None:
        instructions = prompts.get(
            "Instructions", *instruction_args) or prompts.get("SystemInstructions", *instruction_args) or "I am a User you are an AI Assisant, Respond to my messages to aid me"

    return instructions


class AIManager:
    """
    This class is used to manage communication with the AI model.

    Attributes:
        prompts (PromptManager): The prompt manager containing the prompts to be used in the conversation.
        memory (ConversationMemory): The memory object for storing conversation history.
        memoize (dict): A dictionary for storing key-value pairs in the chatbot memory.

    Methods:
        reset_memory(): Resets the memory of the AI manager by clearing the conversation prompt messages and chat memory messages.
        change_instructions(instructions: str): Change the system instructions for the AI chat bot.
        append_to_instructions(prompt_text: str): Append the given prompt_text to the system instructions for the AI chat bot.
        update(key: str, func: Callable, *args, **kwargs): Update the value associated with the given key in the ChatBot memory using the provided function.
        send_chat(message: str) -> dict: Sends a chat message to the AI manager and returns the response.
        get(key: str, default=None): Retrieve the value associated with the given key from the memoize dictionary.
        get_human_messages() -> list: Returns a list of human messages from the AI's memory.
        del_human_messages(): Deletes the most recent human message from the AI's memory.
        get_ai_messages() -> list: Returns the AI messages from the AI's memory.
        send_prompt(prompt: str, *prompt_args, max_tokens=None, temperature=None, model=None, **kwargs): Sends a prompt to the AI model for generating a response.
    """

    # BUG: This function does not work as intended, creates an error when adding memory back.
    def reset_memory(self):
        """
        Resets the memory of the AI manager by clearing the conversation prompt messages and chat memory messages.
        """
        self.conversation.prompt.messages = [self.conversation.prompt.messages[0], MessagesPlaceholder(variable_name="memory"),
                                             HumanMessagePromptTemplate.from_template("{response}")]
        self.memory.chat_memory.messages = []

    def __init__(self, prompts: PromptManager = None, model=MODEL, open_ai_token=TOKEN, temp=0, max_tokens=1000, instructions=None, verbose=False, streaming: bool = False, handle_token: Callable = None, handle_end: Callable = None, handle_start: Callable = None, summarize: bool = True, **kwargs):
        """
        Initialize the AI Manager.

        Args:
            prompts (PromptManager, optional): The prompt manager containing the prompts to be used in the conversation. Defaults to None.
            model (str, optional): The model to be used for generating responses. Defaults to MODEL.
            open_ai_token (str, optional): The OpenAI API token. Defaults to TOKEN.
            temp (float, optional): The temperature value for generating responses. Defaults to 0.
            max_tokens (int, optional): The maximum number of tokens in the generated response. Defaults to 1000.
            instructions (str | tuple, optional): The instructions for the conversation. Defaults to None.
            verbose (bool, optional): Whether to enable verbose mode. Defaults to False.
            streaming (bool, optional): Whether to enable streaming mode. Defaults to False.
            handle_token (Callable, optional): Callback function to handle each generated token. Defaults to None.
            handle_end (Callable, optional): Callback function to handle the end of the conversation. Defaults to None.
            handle_start (Callable, optional): Callback function to handle the start of the conversation. Defaults to None.
            summarize (bool, optional): Whether to enable conversation summarization. Defaults to True.
            **kwargs: Additional keyword arguments.

        Returns:
            None
        """
        instructions = _get_instructions(prompts, instructions)

        handler_class = StreamingStdOutCallbackHandler
        memory_class = ConversationSummaryMemory
        if not summarize:
            memory_class = ConversationBufferMemory

        if handle_token is not None or handle_end is not None or handle_start is not None:
            class AIManager_Callback_Handler(BaseCallbackHandler):
                __out = True

                def on_llm_new_token(self, token: str, **kwargs) -> None:
                    if self.__out:
                        if handle_token is not None:
                            handle_token(token)
                        else:
                            super().on_llm_new_token(token, **kwargs)

                def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], *, run_id: UUID, parent_run_id: UUID | None = None, tags: List[str] | None = None, metadata: Dict[str, Any] | None = None, **kwargs: Any) -> Any:
                    if "Progressively summarize the lines of conversation provided" in prompts[0]:
                        self.__out = False
                    else:
                        self.__out = True
                        if handle_start is not None:
                            handle_start()
                        else:
                            super().on_llm_start(serialized, prompts, run_id=run_id, parent_run_id=parent_run_id,
                                                 tags=tags, metadata=metadata, **kwargs)

                def on_llm_end(self, response: LLMResult, *, run_id: UUID, parent_run_id: UUID | None = None, **kwargs: Any) -> Any:
                    if handle_end is not None:
                        handle_end(
                            response.generations[0][0].message.content)
                        #    finish_reason=response.generations[0][0].generation_info['finish_reason'])
                    else:
                        super().on_llm_end(response, run_id=run_id,
                                           parent_run_id=parent_run_id, **kwargs)

            handler_class = AIManager_Callback_Handler

        callbacks = None
        if streaming:
            callbacks = [handler_class()]

        llm = ChatOpenAI(
            openai_api_key=open_ai_token,
            temperature=temp,
            max_tokens=max_tokens,
            model=model,
            streaming=streaming,
            callbacks=callbacks
        )

        template = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    instructions
                ),
                # The `variable_name` here is what must align with memory
                MessagesPlaceholder(variable_name="memory"),
                HumanMessagePromptTemplate.from_template("{response}")
            ]
        )

        self.prompts = prompts or PromptManager()
        self._max_tokens = max_tokens
        self._temperature = temp
        self._model = model
        self.memory = memory_class(
            memory_key="memory", return_messages=True, llm=llm)
        self.memoize = {}
        if kwargs is not None:
            for key, value in kwargs.items():
                self.memoize[key] = value

        self.conversation = LLMChain(
            llm=llm,
            prompt=template,
            verbose=verbose,
            memory=self.memory
        )

    def change_instructions(self, instructions):
        """
        Change the system instructions for the AI chat bot.

        Args:
            instructions (str): The new instructions for the AI chat bot.

        Returns:
            None
        """
        instructions = _get_instructions(
            prompts=self.prompts, instructions=instructions)
        self.conversation.prompt.messages[0] = SystemMessagePromptTemplate.from_template(
            instructions
        )

    def append_to_instructions(self, prompt_text: str):
        """
        This function appends the given prompt_text to the system instructions for the AI chat bot.

        Parameters:
            prompt_text (str): The text to be appended to the system instructions.

        Returns:
            None
        """
        self.conversation.prompt.messages[0].prompt.template += prompt_text

    def update(self, key: str, func: Callable, *args, **kwargs):
        """
        Update the value associated with the given key in the ChatBot memory using the provided function.

        Parameters:
            key (str): The key to identify the value in the ChatBot memory.
            func (Callable): The function to apply on the value.
            *args: Variable length argument list to be passed to the function.
            **kwargs: Arbitrary keyword arguments to be passed to the function.

        Raises:
            KeyError: If the key is not found in the ChatBot memory.

        Returns:
            None
        """
        if key not in self.memoize:
            raise KeyError(f"Key {key} not found in ChatBot memory")
        else:
            self.memoize[key] = func(self.memoize[key], *args, **kwargs)

    def send_chat(self, message: str):
        """
        Sends a chat message to the AI manager and returns the response.

        Args:
            message (str): The message to be sent.

        Returns:
            dict: The response from the AI manager.
        """
        return self.conversation(
            {"response": message}
        )

    def get(self, key: str, default=None):
        """
        Retrieve the value associated with the given key from the memoize dictionary.

        If the key is found, return the corresponding value. If the key is not found,
        return the default value provided.

        Args:
            key (str): The key to retrieve the value for.
            default: The value to return if the key is not found. Defaults to None.

        Returns:
            The value associated with the key if found, otherwise the default value.
        """
        return self.memoize[key] or default

    def get_human_messages(self):
        """
        Returns a list of human messages from the AI's memory.

        This function retrieves all the messages stored in the AI's memory and filters out
        only the messages sent by humans. It returns a list of the content of those messages.

        Returns:
            list: A list of human messages from the AI's memory.
        """
        return [message.content for message in self.memory.chat_memory.messages if isinstance(message, HumanMessage)]

    def del_human_messages(self):
        """
        Deletes the most recent human message from the AI's memory.

        This function removes the most recent human message from the AI's memory by filtering out all the messages that are instances of the `HumanMessage` class.

        Parameters:
            self (AI_manager): The AI_manager instance.

        Returns:
            None
        """
        self.memory.chat_memory.messages = [
            message for message in self.memory.chat_memory.messages if not isinstance(message, HumanMessage) and "CHAT:" not in message.content]

    def get_ai_messages(self):
        """
        Returns the AI messages from the AI's memory.

        Returns:
            list: A list of AI messages from the AI's memory.
        """
        return [message.content for message in self.memory.chat_memory.messages if isinstance(message, AIMessage)]

    def send_prompt(self, prompt: str, *prompt_args, max_tokens=None, temperature=None, model=None, **kwargs):
        """
        Sends a prompt to the AI model for generating a response.

        Args:
            prompt (str): The prompt to send to the AI model.
            prompt_args: Additional arguments to be passed to the prompt.
            max_tokens (int, optional): The maximum number of tokens to generate in the response. Defaults to None.
            temperature (float, optional): The temperature value for controlling the randomness of the generated response. Defaults to None.
            model (str, optional): The name of the AI model to use for generating the response. Defaults to None.
            **kwargs: Additional keyword arguments to be passed to the prompt.

        Returns:
            str: The generated response from the AI model.
        """
        return self.prompts.send(prompt, *prompt_args, max_tokens=max_tokens or self._max_tokens, temperature=temperature or self._temperature, model=model or self._model, **kwargs)

    def stream_prompt(self, prompt: str, *prompt_args, max_tokens=None, temperature=None, model=None, **kwargs):
        """
        Streams a prompt to the AI model and returns the generated response.

        Args:
            prompt (str): The prompt to be sent to the AI model.
            prompt_args: Additional arguments to be passed to the prompt.
            max_tokens (int, optional): The maximum number of tokens in the generated response. Defaults to None.
            temperature (float, optional): The temperature value for controlling the randomness of the generated response. Defaults to None.
            model (str, optional): The specific model to be used for generating the response. Defaults to None.
            **kwargs: Additional keyword arguments to be passed to the prompt.

        Returns:
            str: The generated response from the AI model.
        """
        return self.prompts.stream(prompt, *prompt_args, max_tokens=max_tokens or self._max_tokens, temperature=temperature or self._temperature, model=model or self._model, **kwargs)
