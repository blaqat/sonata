import os
import importlib

# Import and Add all modules in src/modules/plugins/ to a list
PLUGINS = {}
PLUGINS_ORD = set()

for plugin in os.listdir(os.path.dirname(__file__)):
    if plugin.endswith(".py") and not plugin.startswith("__"):
        module = importlib.import_module("modules.plugins." + plugin[:-3])
        PLUGINS[module.__plugin_name__] = module


# Sort the plugins by their dependencies
def sort_plugins():
    for plugin in PLUGINS:
        if "dependencies" in PLUGINS[plugin].__dict__:
            for dependency in PLUGINS[plugin].__dependencies__:
                if dependency not in PLUGINS_ORD:
                    sort_plugins()
                    break
            else:
                PLUGINS_ORD.add(PLUGINS[plugin])
        else:
            PLUGINS_ORD.add(PLUGINS[plugin])


sort_plugins()
