import os
import importlib

# Import and Add all modules in src/modules/plugins/ to a list
PLUGINS = []


for plugin in os.listdir(os.path.dirname(__file__)):
    if plugin.endswith(".py") and not plugin.startswith("__"):
        PLUGINS.append(importlib.import_module("modules.plugins." + plugin[:-3]))
