import os
import importlib
from collections import defaultdict, deque


def ord_list(l):
    return list(dict.fromkeys(l))


# Import and Add all modules in src/modules/plugins/ to a list
PLUGINS_DICT = {}
PLUGINS_LIST = []

for plugin in os.listdir(os.path.dirname(__file__)):
    if plugin.endswith(".py") and not plugin.startswith("__"):
        module = importlib.import_module("modules.plugins." + plugin[:-3])
        PLUGINS_DICT[module.__plugin_name__] = module
    elif os.path.isdir(os.path.join(os.path.dirname(__file__), plugin)):
        for file in os.listdir(os.path.join(os.path.dirname(__file__), plugin)):
            if file.startswith("module.py"):
                module = importlib.import_module(
                    "modules.plugins." + plugin + "." + file[:-3]
                )
                PLUGINS_DICT[module.__plugin_name__] = module


# Sort the plugins by their dependencies using topological sort
def sort_plugins():
    in_degree = defaultdict(int)
    graph = defaultdict(list)
    sorted_plugins = []

    # Build the graph and in-degree count
    for plugin_name, plugin in PLUGINS_DICT.items():
        if "__dependencies__" in plugin.__dict__ and plugin.__dependencies__:
            for dep in plugin.__dependencies__:
                graph[dep].append(plugin_name)
                in_degree[plugin_name] += 1
        else:
            in_degree[plugin_name] += 0

    # Use deque for efficient pop from left
    zero_in_degree = deque(
        [plugin for plugin in PLUGINS_DICT if in_degree[plugin] == 0]
    )

    while zero_in_degree:
        plugin_name = zero_in_degree.popleft()
        sorted_plugins.append(plugin_name)
        for dependent in graph[plugin_name]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                zero_in_degree.append(dependent)

    global PLUGINS_LIST
    PLUGINS_LIST = [PLUGINS_DICT[plugin] for plugin in sorted_plugins]


def PLUGINS(extend: list = None, mode: str = "allow", **kwags):
    plugins = PLUGINS_LIST.copy()
    included_plugins = set(plugin.__plugin_name__ for plugin in plugins)

    # Determine which plugins are enabled based on extend and kwags
    if extend is not None:
        if mode == "allow":
            plugins = [
                PLUGINS_DICT[plugin] for plugin in PLUGINS_DICT if plugin in extend
            ]
        elif mode == "deny":
            plugins = [
                PLUGINS_DICT[plugin] for plugin in PLUGINS_DICT if plugin not in extend
            ]
        else:
            raise ValueError("Mode must be either 'allow' or 'deny'")

    # Apply additional kwags to include or exclude specific plugins
    for k, v in kwags.items():
        if v and k in PLUGINS_DICT and PLUGINS_DICT[k] not in plugins:
            plugins.append(PLUGINS_DICT[k])
        elif not v and k in PLUGINS_DICT and PLUGINS_DICT[k] in plugins:
            plugins.remove(PLUGINS_DICT[k])

    # Rebuild the list of included plugin names after kwags adjustments
    included_plugins = set(plugin.__plugin_name__ for plugin in plugins)

    # Ensure dependencies are respected and added only if their dependents are included
    resolved_plugins = []
    dependencies_map = {
        plugin.__plugin_name__: set(plugin.__dependencies__)
        if "__dependencies__" in plugin.__dict__
        else set()
        for plugin in PLUGINS_DICT.values()
    }

    def add_plugin_with_deps(plugin_name):
        if plugin_name in resolved_plugins:
            return
        for dep in dependencies_map.get(plugin_name, []):
            if dep not in resolved_plugins:
                add_plugin_with_deps(dep)
        resolved_plugins.append(plugin_name)

    for plugin in plugins:
        add_plugin_with_deps(plugin.__plugin_name__)

    # Ensure that the final list contains only the required plugins and their necessary dependencies
    final_plugins = [
        PLUGINS_DICT[plugin]
        for plugin in resolved_plugins
        if plugin in included_plugins
        or any(dep in included_plugins for dep in dependencies_map[plugin])
    ]

    return ord_list(final_plugins)


sort_plugins()
