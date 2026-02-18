"""
General utilities module.

This module contains various utility functions that can be used across different projects.
"""

__author__ = "Aiden Green"
__email__ = "aidengreenj@gmail.com"

from functools import reduce
import os
import traceback
from typing import Any, Callable, Union, Iterable, Literal
from os import getenv
from annotated_types import IsInfinite
from discord.colour import Color
from typing_extensions import cast
from dotenv import load_dotenv
import asyncio
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
import requests
import threading
import queue
import time

import re
from concurrent.futures import ThreadPoolExecutor


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)).replace("src/modules", "")
# def run_async_coroutine(coroutine):
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     result = loop.run_until_complete(coroutine)
#     loop.close()
#     return result
#
#
# def execute(func, *args, **kwargs):
#     with ThreadPoolExecutor() as executor:
#         future = executor.submit(run_async_coroutine, func(*args, **kwargs))
#         return future.result()
#

load_dotenv()


def check_inside(a, b):
    """
    Check if any element in  'a' is present in 'b'.

    Returns:
        bool: True if any element in 'a' is present in 'b', False otherwise.
    """
    for i in a:
        if i in b:
            return True
    return False


def broadcast(clients, func, *args, **kwargs):
    """
    Broadcasts a function call to all clients.

    Args:
        clients (dict): A dictionary of clients.
        func (function): The function to be called for each client.
        *args: Variable length argument list to be passed to the function.
        **kwargs: Arbitrary keyword arguments to be passed to the function.
    """
    for client in clients.values():
        func(client, *args, **kwargs)


class _ENV:
    def __getattribute__(self, __name: str) -> Any:
        return getenv(__name)


settings = _ENV()


class Enum:
    _fields = {}
    _reverse_fields = {v: k for k, v in _fields.items()}

    def __init__(self, name=None, value=None):
        if name is None and value is None:
            self.VALUE = list(self._fields.values())
            self.NAME = list(self._fields.keys())
        elif name is None and value is not None:
            name = self.name_of(value)
            if name is None:
                raise ValueError(f"Invalid value {value}")
            self.NAME = name
            self.VALUE = value
        elif name is not None:
            name = name.lower()
            val = self.value_of(name)
            if val is None:
                raise ValueError(f"Invalid name {name}")
            self.NAME = name
            self.VALUE = val

    def __getitem__(self, key):
        return self.from_name(key)

    def __getattr__(self, key) -> Any:
        return self.from_name(key)

    @classmethod
    def value_of(cls, name):
        return cls._fields.get(name.lower(), None)

    @classmethod
    def name_of(cls, value):
        return cls._reverse_fields.get(value, None)

    def from_val(self, value):
        return Enum(value=value, name=self._reverse_fields[value])

    def from_name(self, name):
        if name.isinstance(str):
            name = name.lower()
        return Enum(value=self._fields[name], name=name)

    @classmethod
    def on_match_index(cls, **cases):
        _MATCH = cls.on_match(**cases)
        _NAMES = cls.names(cls)
        return lambda i: _MATCH(_NAMES[i])

    @classmethod
    def on_match(cls, **cases):
        def match(value):
            if value.isinstance(cls):
                value = value.NAME
            for k, v in cases.items():
                k = k.lower()
                if k.lower() == value:
                    if callable(v):
                        return v()
                    return v
            return cases.get("default", lambda: None)()

        return match

    def match(self, value=None, **cases):
        if not value:
            value = self.NAME
        elif value.isinstance(self):
            value = value.NAME
        for k, v in cases.items():
            k = k.lower()
            if k.lower() == value:
                if callable(v):
                    return v()
                return v
        return cases.get("default", lambda: None)()

    @classmethod
    def match_pair(
        cls, values: tuple, patterns: dict[tuple | None, Any], default=lambda: None
    ):
        for pattern, action in patterns.items():
            if pattern is None:
                default = action
                break
            elif all(
                val in pat if isinstance(pat, tuple) else (pat is None) or (val == pat)
                for val, pat in zip(values, pattern)
            ):
                if callable(action):
                    return action()
                return action
        if callable(default):
            return default()
        return default

    def __str__(self):
        if self.VALUE.isinstance(list):
            return f"{self.__class__.__name__} {self._fields}"

        # return str(self._fields) + str(self.VALUE)
        return f"{self.__class__.__name__} [{self.NAME}: {self.VALUE}]"

    def __eq__(self, other):
        if type(other) is self.__class__:
            return self.VALUE == other.VALUE and self.NAME == other.NAME
        return self.VALUE == other or self.NAME == other.lower()

    def __hash__(self):
        return hash(self.VALUE) + hash(self.NAME)

    def names(self):
        return list(self._fields.keys())


class bcolors:
    """
    Colors:
    PURPLE, BLUE, CYAN, GREEN, YELLOW, RED
    _0: Reset color
    B: Bold
    _: Underline
    """
    PURPLE = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    _0 = "\033[0m"
    B = "\033[1m"
    BOLD = "\033[1m"
    _ = "\033[4m"
    UNDERLINE = "\033[4m"


BColor = Literal[
    "_",
    "underline",
    "b",
    "bold",
    "_0",
    "purple",
    "blue",
    "cyan",
    "green",
    "yellow",
    "red",
]

class Colors(Enum):
    PURPLE = "purple"
    BLUE = "blue"
    CYAN = "cyan"
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    RESET = "_0"
    BOLD = "b"
    UNDERLINE = "_"

__input = input


def clear():
    """
    Clears the console.
    """
    print("\033c", end="")


def input(
    prompt: str,
    valid_input: bool | list | Callable = True,
    case_sensitive: bool = False,
    return_type: type | Callable = str,
    fail_msg: str = "",
    input_color: str = None,
):
    """
    Prompts the user for input and validates it against a list of valid inputs.

    Args:
        prompt (str): The prompt to display to the user.
        valid_input (bool | list, optional): A list of valid inputs. Defaults to True.
        case_sensitive (bool, optional): Whether or not the input is case sensitive. Defaults to False.
        return_type (type, optional): The type to return the input as. Defaults to str.

    Returns:
        str: The user's input.
    """
    while True:
        user_input = __input(prompt + (__get_color(input_color) if input_color else ""))
        print(end=f"{bcolors._0}")
        if case_sensitive is False:
            user_input = user_input.lower()
        if valid_input.isinstance(bool) and valid_input is not True:
            raise ValueError("valid_input must be a list or function if not True.")
        try:
            if (
                valid_input is True
                or callable(valid_input)
                and valid_input(return_type(user_input))
                or valid_input.isinstance(list)
                and user_input in valid_input
            ):
                return return_type(user_input)
        except ValueError:
            pass

        msg = "Invalid input. "
        msg += (
            fail_msg
            or f"""Input must be one of the following: {
            valid_input}"""
        )
        if case_sensitive:
            msg += "Reminder: input is case sensitive."
        print(msg)


def filter_loop(
    iterations: int | bool,
    func: Callable,
    *args,
    filter_by: Callable | None = None,
    filter_args: list = [],
    **kwargs,
) -> list:
    return loop(
        iterations,
        func,
        *args,
        check=filter_by,
        check_args=filter_args,
        break_on_failed_check=False,
        **kwargs,
    )


def loop(
    iterations: int | bool,
    func: Callable,
    *args,
    check: Callable | None = None,
    check_args: list = [],
    break_on_failed_check: bool = True,
    **kwargs,
) -> list:
    """
    Runs a function a specified number of times.

    Args:
        iterations (int): The number of times to run the function.
        func (callable): The function to run.
        *args: The arguments to pass to the function.
        **kwargs: The keyword arguments to pass to the function.

    Returns:
        list: A list containing the results of each iteration.

    """
    results = []

    iterations = iterations if iterations.isinstance(int) else -1
    i = 0

    iterator_vals = [
        "loop_i",
        "iteration",
        "loop_j",
        "loop_index",
        "loop_k",
        "loop_key",
        "loop_x",
        "_i",
        "_j",
        "_k",
        "_x",
    ]
    result_vals = ["loop_result", "result", "loop_r", "_r"]
    # Get check arguments
    c_args = []
    if (
        check
        and len(check.__code__.co_varnames) > 0
        and check.__code__.co_varnames[0] in iterator_vals
    ):
        c_args.append(i)
    elif (
        check
        and len(check.__code__.co_varnames) > 0
        and check.__code__.co_varnames[0] in result_vals
    ):
        c_args.append(results)
    c_args.extend(check_args)
    while iterations > 0 or iterations == -1:
        if not (check is None or check(*c_args)):
            if break_on_failed_check or iterations == -1:
                break
            else:
                iterations -= 1
                i += 1
                continue
        # Check if function wants i passed through
        if (
            len(func.__code__.co_varnames) > 0
            and func.__code__.co_varnames[0] in iterator_vals
        ):
            results.append(func(i, *args, **kwargs))
        elif (
            len(func.__code__.co_varnames) > 0
            and func.__code__.co_varnames[0] in result_vals
        ):
            results.append(
                func(results[-1] if len(results) > 0 else None, *args, **kwargs)
            )
        else:
            results.append(func(*args, **kwargs))
        iterations -= 1 if iterations != -1 else 0
        i += 1

    return results


def __is_argsable(obj: Any) -> bool:
    """
    Checks if an object is argsable.

    Args:
        obj (Any): The object to check.

    Returns:
        bool: Whether or not the object is argsable.

    """
    try:
        tuple(obj)
        return True
    except TypeError:
        return False


def propogate(
    *ordered_funcs,
    starting_args: Any = None,
    expected_results: list[str] | None = None,
    is_callable: bool = False,
    **named_funcs: Callable,
) -> Any:
    """
    Propogates the results of one function to the next.

    Args:
        *funcs (Callable): A list of functions to call in order.
        starting_args (list, optional): A list of arguments to pass to the first function. Defaults to [].
        expected_results (list[str], optional): A list of keys for the expected results. Defaults to [].
        **named_funcs (Callable): A dictionary of named functions to call after the unnamed functions.

    Returns:
        Any: The final result of the last function call.

    """
    if is_callable:
        return lambda: propogate(
            *ordered_funcs,
            starting_args=starting_args,
            expected_results=expected_results,
            is_callable=False,
            **named_funcs,
        )

    result = {}

    if starting_args is not None and not named_funcs:
        if type(starting_args) is Union[list, dict, tuple, Iterable]:
            result = tuple(starting_args)
        else:
            result = starting_args
    elif starting_args.isinstance(list):
        for i, arg in enumerate(starting_args):
            result[f"arg{i}"] = arg
    elif starting_args.isinstance(dict):
        result = starting_args

    _CAPTURED = result

    for name, func in named_funcs.items():
        result[name] = func()

    for func in ordered_funcs:
        if not callable(func):
            result = func
        elif result.isinstance(dict):
            result = func(**result)
        elif result.isinstance(tuple):
            result = func(*result)
        elif result is None:
            result = func()
        else:
            result = func(result)

    if expected_results is not None:
        if result.isinstance(dict):
            for r_name in expected_results:
                if r_name not in result:
                    raise ValueError(f"Result does not contain {r_name}.")
        elif (len(expected_results) >= 1 and result is not None) and (
            (len(expected_results) != 1 and not __is_argsable(result))
            or (
                len(expected_results) >= 1
                and __is_argsable(result)
                and len(result) != len(expected_results)
            )
        ):
            raise ValueError(
                f"Result must contain dictionary with keys {expected_results} OR a iterable with length {len(expected_results)}. Actual length: {len(result)}"
            )
        elif (
            len(expected_results) == 1
            and result is not None
            and not __is_argsable(result)
        ):
            return {expected_results[0]: result}
        else:
            raise ValueError(
                f"ValueError: The expected result is not returned. Expected: {expected_results}"
            )

    return result


def rprint(*args, ret=None, **kwargs):
    print(*args, **kwargs)
    return ret


def enum(*unnamed_fields: Any, **named_fields: Any):
    """
    Creates an enumeration object.

    Args:
        sequential: A list of names for the enum.
        named: A dictionary of names and explicit values for the enum.

    Returns:
        namedtuple: An enumeration object.

    Raises:
        ValueError: If there are duplicate names or values.
    """
    fields = {}
    used_values = set()

    # Named fields first to reserve their values
    for name, value in named_fields.items():
        fields[name] = value
        used_values.add(value)

    # Start next_value from 0
    next_value = 0

    # Unnamed fields next, starting from next_value to avoid overlapping with named fields
    for field in unnamed_fields:
        lower_field = field.lower()
        if lower_field not in fields:  # Avoid overlapping
            while next_value in used_values:
                next_value += 1
            fields[lower_field] = next_value
            used_values.add(next_value)
            next_value += 1

    class InnerEnum(Enum):
        _fields = fields
        _reverse_fields = {v: k for k, v in fields.items()}

        def from_val(self, value):
            return InnerEnum(value=value, name=self._reverse_fields[value])

        def from_name(self, name):
            if name.isinstance(str):
                name = name.lower()
            return InnerEnum(value=self._fields[name], name=name)

    for name, value in fields.items():
        setattr(InnerEnum, name, InnerEnum(value=value, name=name))

    InnerEnum.__name__ = "Enum"

    _first_item_in_field = next(iter(fields))
    return InnerEnum(), InnerEnum


def __get_color(color: str):
    if not color:
        return ""
    return bcolors.__getattribute__(bcolors, color.upper())


def cstr(str, style: str | Color | None):
    if not style:
        return str

    if isinstance(style, Color):
        st = rgb_to_terminal_color(*style.to_rgb())
    else:
        st = __get_color(style)

    return f"{st}{str}{bcolors._0}"

def cstrs(str, *styles):
    return reduce(lambda s, c: cstr(s, c), styles, str)

def cprint(str: str, *styles: str, end="\n"):
    """
    Prints a string with color.

    Args:
        str (str): The string to print.
        *styles (str): The styles to apply to the string.
    """

    print(cstrs(str, *styles), end=end)


# Global prompt session and helper prompts for PromptToolkit-based terminal I/O
PROMPT_SESSION = PromptSession()


class E(Exception):
    """Shared terminal prompt exit exception."""
    pass


async def prompt(
    text,
    convert=None,
    exit_if=None,
    exit_msg=None,
    color: BColor | None = None,
    exit_callback: Callable = None,
):
    """Prompt using the global PromptSession. Mirrors the behavior expected by
    the terminal plugin: returns converted value, raises `E` on `exit` or
    invalid conversions/conditions.
    """
    with patch_stdout():
        x = await PROMPT_SESSION.prompt_async(text if not color else ANSI(cstr(text, color)))
    if x == "exit":
        if exit_callback is not None:
            exit_callback()
        raise E
    if convert is not None:
        x = convert(x)
        if x is None:
            cprint(exit_msg or "Invalid conversion", "red")
            raise E
    if exit_if is not None and exit_if(x):
        if exit_msg is not None:
            cprint(exit_msg, "red")
        raise E
    return x


async def editable_prompt(
    text: str,
    current: str,
    convert=None,
    exit_if=None,
    exit_msg=None,
    color: BColor | None = None,
    exit_callback: Callable = None,
):
    """Editable Prompt that shows the current value and allows the user to edit it
    using the shared PromptSession.
    """
    with patch_stdout():
        x = await PROMPT_SESSION.prompt_async(
            text if not color else ANSI(cstr(text, color)), default=current
        )
    if x == "exit":
        if exit_callback is not None:
            exit_callback()
        raise E
    if convert is not None:
        x = convert(x)
        if x is None:
            cprint(exit_msg or "Invalid conversion", "red")
            raise E
    if exit_if is not None and exit_if(x):
        if exit_msg is not None:
            cprint(exit_msg, "red")
        raise E
    return x


def print_symbols(
    *symbol: str | Enum,
    padding: int = 1,
    allign: int | str = 0,
    colors: list | Callable = [],
):
    # Split symbols by lines
    symbols = [
        (s if s.isinstance(str) else s.VALUE).split("\n") for i, s in enumerate(symbol)
    ]
    max_height = 0
    max_widths = []

    # Get max height and max width for each symbol
    for s in symbols:
        max_height = max(max_height, len(s))
        max_widths.append(max(len(line) for line in s))

    # Keep smaller symbols centered vertically
    for i, s in enumerate(symbols):
        height = len(s)
        # Add trailing spaces to symbols
        if auto_trailing:
            for j, line in enumerate(s):
                s[j] = line.ljust(max_widths[i])
        # Allign symbols
        if allign != 0 and allign != "top" and height < max_height:
            loop(
                (
                    (max_height - height) // 2
                    if allign == 1 or allign == "center"
                    else max_height - height - 0
                ),
                lambda: s.insert(0, " " * max_widths[i]),
            )

    # Build new string, then print
    return propogate(
        loop(
            max_height,
            lambda _i: "".join(
                loop(
                    len(symbols),
                    lambda _j: cstr(
                        (
                            symbols[_j][_i]
                            if _i < len(symbols[_j])
                            else " " * max_widths[_j]
                        )
                        + " " * padding,
                        (
                            colors[_j]
                            if not callable(colors) and len(colors) > _j
                            else colors(symbol[_j]) if callable(colors) else None
                        ),
                    ),
                )
            ),
        ),
        lambda s: "\n".join(s[:-1]).rstrip(),
        print,
    )


def picker(choices: list = [], delay_count=0, reverse_on_end: bool = False):
    last = -1
    i = 0
    direction = 1

    def pick(_i):
        nonlocal i, last, direction
        i = _i if _i else i
        if i % delay_count == 0:
            if last == len(choices) - 1:
                direction = -1
            elif last == 0:
                direction = 1
            last += direction
            last %= len(choices)
        i += 1
        return choices[last]

    return pick


def clamp(value, min_value, max_value):
    return max(min(value, max_value), min_value)


def has_inside(str, list):
    for i in list:
        if i in str:
            return True
    return False


def inside(a, b):
    pattern = re.compile(re.escape(a), re.IGNORECASE)
    return pattern.search(b) is not None


def find_matches(a, b):
    pattern = re.compile(re.escape(a), re.IGNORECASE)
    return pattern.findall(b)


def setter(thing, key, value, **kwargs):
    if key is not None:
        thing[key] = value
    for k, v in kwargs.items():
        thing[k] = v
    return thing


def runner(thing, key, *args, r=False, **kwargs):
    x = thing.__getattribute__(key)(*args, **kwargs)
    if r:
        return x
    return thing


def censor_message(message, banned_words):
    return re.sub(
        "|".join([re.escape(word) for word in banned_words]),
        lambda m: "#" * len(m.group()),
        message,
        flags=re.IGNORECASE,
    )


def get_full_name(ctx):
    try:
        author = ctx.author
        name = author.name
        if "nick" in dir(author) and author.nick is not None:
            name += f" (Nickname: {author.nick})"
        return name
    except AttributeError as _:
        async_cprint("Error get_full_name defaulting to sonata", "red")
        return "sonata"


# def async_print(*args, **kwargs):
#     try:
#         loop = asyncio.get_running_loop()
#         loop.run_in_executor(None, print, *args, **kwargs)
#     except Exception as e:
#         print(*args, **kwargs)


# def async_cprint(*args, **kwargs):
#     try:
#         loop = asyncio.get_running_loop()
#         loop.run_in_executor(None, cprint, *args, **kwargs)
#     except Exception as e:
#         cprint(*args, **kwargs)

class NonBlockingPrinter:
    ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

    def __init__(self, max_queue_size=0):
        self.print_queue = queue.Queue(maxsize=max_queue_size)
        self.worker_thread = None
        self.running = False
        self._start_worker()

    def _start_worker(self):
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.running = True
            self.worker_thread = threading.Thread(
                target=self._print_worker, daemon=True
            )
            self.worker_thread.start()

    def _run_in_terminal(self, callable_obj):
        """Try to run callable in shared PromptSession app, or fallback."""
        # Prefer session app runner
        try:
            app = getattr(PROMPT_SESSION, "app", None)
            if app is not None and hasattr(app, "run_in_terminal"):
                try:
                    return app.run_in_terminal(callable_obj)
                except Exception:
                    pass
        except Exception:
            pass

        # Fallback to prompt_toolkit.shortcuts.run_in_terminal if available
        try:
            from prompt_toolkit.shortcuts import run_in_terminal

            try:
                return run_in_terminal(callable_obj)
            except Exception:
                pass
        except Exception:
            pass

        # Last resort: direct call
        try:
            return callable_obj()
        except Exception:
            return None

    def _print_worker(self):
        """Worker that handles queued print jobs."""
        try:
            from prompt_toolkit.shortcuts import print_formatted_text
            from prompt_toolkit.formatted_text import ANSI as PTK_ANSI
        except Exception:
            print_formatted_text = None
            PTK_ANSI = None

        while self.running:
            try:
                job = self.print_queue.get(timeout=1.0)
                if job is None:
                    break

                kind, payload = job
                match kind:
                    case "call":
                        func, args, kwargs = payload

                        def _call():
                            func(*args, **(kwargs or {}))

                        self._run_in_terminal(_call)

                    case "text":
                        text, kwargs = payload
                        if self.ANSI_RE.search(text) and print_formatted_text is not None and PTK_ANSI is not None:
                            def _call_pf():
                                print_formatted_text(PTK_ANSI(text), **(kwargs or {}))

                            self._run_in_terminal(_call_pf)
                        else:
                            self._run_in_terminal(lambda: print(text, **(kwargs or {})))

                try:
                    self.print_queue.task_done()
                except Exception:
                    pass

                time.sleep(0.001)

            except queue.Empty:
                continue
            except Exception:
                continue

    def queue_text(self, text: str, **kwargs):
        try:
            self.print_queue.put(("text", (text, kwargs)), block=False)
        except queue.Full:
            pass

    def queue_call(self, func: Callable, *args, **kwargs):
        try:
            self.print_queue.put(("call", (func, args, kwargs)), block=False)
        except queue.Full:
            pass

    def shutdown(self):
        self.running = False
        try:
            self.print_queue.put(None, block=False)
        except:
            pass


_printer = NonBlockingPrinter()


def async_print(*args, sep=" ", **kwargs):
    """Non-blocking print - queues the job"""
    _printer.queue_text(sep.join(str(arg) for arg in args), **kwargs)


def async_cprint(text, *styles, **kwargs):
    """Non-blocking colored print - queues the job"""
    async_print(cstrs(text, *styles), **kwargs)


def async_input(*args, **kwargs):
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, __input, *args, **kwargs)


def print_list(lst, color=None):
    async_cprint("\n".join("{}: {}".format(*k) for k in enumerate(lst)), color)


def print_available_genai_models(genai):
    async_print("\n".join("{}".format(k.name[7:]) for k in genai.list_models()))


# TODO: Store in Sona.memory to allow for saving/loading
# Stored as ID: (message, name, content, next id)
class Reference:
    def __init__(self, message, name, content, next_id):
        self.message = message
        self.author = name
        self.content = content
        self.next_id = next_id


references = {}


def store_reference(message):
    ref = Reference(
        message,
        message.author.name,
        message.content,
        message.reference.message_id if message.reference else None,
    )

    references[message.id] = ref

    return ref


async def get_next_reference(message):
    if message.id not in references:
        store_reference(message)

    next_id = references[message.id].next_id

    if next_id is None:
        return None

    if next_id not in references:
        return store_reference(await message.channel.fetch_message(next_id))

    return references[next_id]


async def get_reference_message(message, return_message=True):
    if message.reference is None:
        return None

    ref_message = await get_next_reference(message)

    return ref_message.message if return_message else ref_message


async def get_reference_chain(message, max_length=-1, include_message=False):
    if message is None:
        return None

    chain = []
    if include_message:
        chain.append((message.author.name, message.content))

    if message is None or message.reference is None:
        return chain if include_message else None

    reference = await get_reference_message(message, return_message=False)

    while reference is not None and max_length != 0:
        chain.append((reference.author, reference.content))
        if reference.next_id is None:
            break
        reference = await get_reference_message(reference.message, return_message=False)
        max_length -= 1

    if len(chain) == 0:
        return None

    if max_length == 0:
        return chain[0]

    chain.reverse()
    return chain


def tenor_get_dl_url(url, key, size="mediumgif"):
    gif_id = None
    try:
        gif_id = re.search(r"-(\d+)$", url).group(1)
    except AttributeError:
        return None

    if not gif_id:
        return None

    api_url = f"https://tenor.googleapis.com/v2/posts?ids={gif_id}&key={key}"
    response = requests.get(api_url)

    if response.status_code == 200:
        data = response.json()
        if data and "results" in data and len(data["results"]) > 0:
            formats = data["results"][0]["media_formats"]
            if size not in formats:
                cprint(f"Invalid size {size}. Available sizes: {formats.keys()}")
                # Find first one with tiny
                for key in formats.keys():
                    if "nano" in key and ("gif" in key or "webp" in key):
                        size = key
                        break
                else:
                    for key in formats.keys():
                        if "tiny" in key and ("gif" in key or "webp" in key):
                            size = key
                            break
                cprint(f"Replaced with {size}")
            data["results"][0]["media_formats"][size]["url"]
            medium_gif_url = (
                data.get("results", [{}])[0]
                .get("media_formats", [{}])
                .get("mediumgif", {})
                .get("url", None)
            )
            if medium_gif_url:
                return medium_gif_url
            else:
                return None
        else:
            return None
    else:
        return None


class Map:
    def __init__(self, initial_dict: dict = None):
        self._data: dict = initial_dict if initial_dict is not None else dict()

    def __getattr__(self, key):
        try:
            if key == "_data":
                return super().__getattribute__(key)
            else:
                return self._data[key]
        except KeyError:
            return self._data.__getattribute__(key)

    def __setattr__(self, key, value):
        if key == "_data":
            super().__setattr__(key, value)
        else:
            self._data[key] = value

    def __delattr__(self, key):
        try:
            del self._data[key]
        except KeyError:
            raise AttributeError(f"'Dict' object has no attribute '{key}'")

    def __getitem__(self, key):
        return self._data[key]

    def __setitem__(self, key, value):
        self._data[key] = value

    def __delitem__(self, key):
        del self._data[key]

    def __contains__(self, key):
        return key in self._data

    def to_dict(self):
        return self._data.copy()


class RestartSignal(Exception):
    """Exception raised to signal a restart is required."""

    pass


def get_trace() -> str:
    tb = traceback.format_exc()
    tb = tb.replace(PROJECT_ROOT, "")
    return tb


def ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1:'st', 2:'nd', 3:'rd'}.get(n % 10, 'th')}"

def rgb_to_terminal_color(r, g, b):
    return f"\033[38;2;{r};{g};{b}m"


def safe_get(obj, *attrs, default=None):
    for attr in attrs:
        try:
            obj = getattr(obj, attr)
        except AttributeError:
            return default
    return obj
