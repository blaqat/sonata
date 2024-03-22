import os
import importlib
from collections import OrderedDict


def ord_list(l):
    return list(dict.fromkeys(l))


# Import and Add all modules in src/modules/plugins/ to a list
PLUGINS_DICT = {}
PLUGINS_LIST = set()

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


# Sort the plugins by their dependencies
def sort_plugins():
    sorted_plugins = []
    dependencies_map = {}
    no_deps = []

    # Build a map of dependencies and list of plugins with no dependencies
    for plugin_name, plugin in PLUGINS_DICT.items():
        if "__dependencies__" in plugin.__dict__ and plugin.__dependencies__:
            dependencies_map[plugin_name] = set(plugin.__dependencies__)
        else:
            no_deps.append(plugin_name)

    # Function to add plugins to sorted list, ensuring dependencies are added first
    def add_plugin(plugin_name):
        if plugin_name in sorted_plugins:
            return
        for dep in dependencies_map.get(plugin_name, []):
            if dep not in sorted_plugins:
                add_plugin(dep)
        sorted_plugins.append(plugin_name)

    # Add plugins with no dependencies first
    for plugin_name in no_deps:
        add_plugin(PLUGINS_DICT[plugin_name])

    # Add remaining plugins, ensuring their dependencies are resolved
    for plugin_name in dependencies_map:
        add_plugin(PLUGINS_DICT[plugin_name])

    global PLUGINS_LIST
    PLUGINS_LIST = sorted_plugins


def PLUGINS(extend: list = None, mode: str = "allow", **kwags):
    if extend is None:
        return PLUGINS_LIST
    dependencies = []
    plugins = None
    if mode == "allow":
        plugins = [PLUGINS_DICT[plugin] for plugin in PLUGINS_DICT if plugin in extend]
    elif mode == "deny":
        plugins = [
            PLUGINS_DICT[plugin] for plugin in PLUGINS_DICT if plugin not in extend
        ]
    else:
        raise ValueError("Mode must be either 'allow' or 'deny'")

    for k, v in kwags.items():
        if v == True:
            plugins.append(PLUGINS_DICT[k])

        if v == False:
            plugins.remove(PLUGINS_DICT[k])

    # Find all dependencies of the plugins
    found_new = True
    while found_new:
        found_new = False
        for plugin in plugins:
            if "__dependencies__" not in plugin.__dict__:
                continue
            for dependency in plugin.__dependencies__:
                d = PLUGINS_DICT[dependency]
                if d not in dependencies:
                    dependencies.insert(0, d)
                    found_new = True

    return ord_list(dependencies + plugins)


sort_plugins()
