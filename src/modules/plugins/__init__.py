import os
import importlib
from collections import OrderedDict

# Import and Add all modules in src/modules/plugins/ to a list
PLUGINS = {}
PLUGINS_ORD = set()

for plugin in os.listdir(os.path.dirname(__file__)):
    if plugin.endswith(".py") and not plugin.startswith("__"):
        module = importlib.import_module("modules.plugins." + plugin[:-3])
        PLUGINS[module.__plugin_name__] = module


# Sort the plugins by their dependencies
def sort_plugins():
    sorted_plugins = []
    dependencies_map = {}
    no_deps = []

    # Build a map of dependencies and list of plugins with no dependencies
    for plugin_name, plugin in PLUGINS.items():
        if "dependencies" in plugin.__dict__ and plugin.__dependencies__:
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
        add_plugin(PLUGINS[plugin_name])

    # Add remaining plugins, ensuring their dependencies are resolved
    for plugin_name in dependencies_map:
        add_plugin(PLUGINS[plugin_name])

    global PLUGINS_ORD
    PLUGINS_ORD = sorted_plugins


sort_plugins()
