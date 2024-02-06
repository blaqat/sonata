"""
General utilities module.

This module contains various utility functions that can be used across different projects.
"""

__author__ = "Aiden Green"
__email__ = "aidengreenj@gmail.com"

from typing import Any, Callable, Union, Iterable
from os import getenv
from dotenv import load_dotenv

import re
from concurrent.futures import ThreadPoolExecutor


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
    PURPLE = "\033[95m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    _0 = "\033[0m"
    B = "\033[1m"
    _ = "\033[4m"


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


def cstr(str, style):
    if not style:
        return str

    st = __get_color(style)
    return f"{st}{str}{bcolors._0}"


def cprint(str: str, *styles: str, end="\n"):
    """
    Prints a string with color.

    Args:
        str (str): The string to print.
        *styles (str): The styles to apply to the string.
    """
    for st in styles:
        str = f"{__get_color(st)}{str}"
    str += bcolors._0
    print(str, end=end)


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
                (max_height - height) // 2
                if allign == 1 or allign == "center"
                else max_height - height - 0,
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
                        colors[_j]
                        if not callable(colors) and len(colors) > _j
                        else colors(symbol[_j])
                        if callable(colors)
                        else None,
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


def inside(a, b):
    pattern = re.compile(re.escape(a), re.IGNORECASE)
    return pattern.search(b) is not None


def find_matches(a, b):
    pattern = re.compile(re.escape(a), re.IGNORECASE)
    return pattern.findall(b)


def setter(thing, key, value):
    thing[key] = value
    return thing


def runner(thing, key, *args, r=False, **kwargs):
    x = thing.__getattribute__(key)(*args, **kwargs)
    if r:
        return x
    return thing
