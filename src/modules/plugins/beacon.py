"""
  _^_
  |@|    Beacon - when you're lost this is the light that will find you.
 =====
  #::
  #::
  #::
  #::
  #::
  #::
###::^-..
         ^ ~ ~~ ~~ ~ ~ ~
          \\~~ ~~ ~ ~  ~~~~~
-----------
This plugin is a basic file serialization plugin that allows you to save and load data from files.
It is useful for saving data that you want to persist between sessions.
Can also create island folders to save data in.
"""

from modules.utils import (
    async_cprint as cprint,
    async_print as print,
)
from modules.AI_manager import AI_Manager
from typing import Literal

import pickle
import os
import shutil

L, M, P = AI_Manager.init(lazy=True)
__plugin_name__ = "beacon"
dir_path = os.path.dirname(os.path.realpath(__file__))

SaveType = Literal["m", "c", None]


def can_delete_folder(folder_path):
    # Check if the folder is empty or contains .p files
    for _, dirs, files in os.walk(folder_path):
        if not files and not dirs:
            return True
        for file in files:
            if file.endswith(".p"):
                return True
    return False


@M.builder
def beacon(sonata: AI_Manager):
    def parse_save_type(name, d, t):
        if t == "m":
            if type(d) == dict:
                return sonata.get(name, **d)
            elif type(d) == list or type(d) == tuple:
                return sonata.get(name, *d)
            elif type(d) == str:
                print(name, d)
                return sonata.get(name, d)
            else:
                return sonata.get(name)
        elif t == "c":
            return sonata.config.get(name)
        return None

    class Beacon:
        home: str  # The home folder where things are saved

        def __init__(self, path: str = "beacon-mainland"):
            self.light_house(path, True)

        def island(self, path: str, home=False):
            """Set the home folder"""
            l = Beacon()
            l.light_house(path, home)
            return l

        def branch(self, path: str):
            """Create a new folder"""
            return self.island(f"{self.home}/{path}")

        def light_house(self, path: str, home=False):
            """Set the home folder"""
            self.home = (f"{dir_path}/" if home else "") + path
            if not os.path.exists(self.home):
                os.mkdir(self.home)
            return self

        def scan(self):
            """List all the files in the home folder"""
            return os.listdir(self.home)

        def guide(self, name: str, data: any = None, remember: SaveType = None):
            """Save data to a file"""
            if remember != None:
                data = parse_save_type(name, data, remember)

            if data is None:
                cprint(f"Can not light up the path, {name} is not found.", "red")
                return

            with open(f"{self.home}/{name}.p", "wb") as f:
                pickle.dump(data, f)

            return self

        def locate(self, name: str):
            """Load data from a file"""
            try:
                with open(f"{self.home}/{name}.p", "rb") as f:
                    return pickle.load(f)
            except:
                cprint(f"Can not locate the path, {name} is not found.", "red")
                return

        def illuminate(self, module_name: str, data: dict, remember: SaveType = None):
            """Save module to a file"""
            if remember != None:
                data = parse_save_type(module_name, data, remember)

            if data is None:
                cprint(
                    f"Can not illuminate the module, {module_name} is not found.", "red"
                )
                return

            lamp_post = self.branch(module_name)
            for key, value in data.items():
                t = ""

                if type(key) == int:
                    t = "i"
                elif type(key) == float:
                    t = "f"
                elif type(key) == bool:
                    t = "b"
                else:
                    t = "s"

                lamp_post.guide(f"{t}{key}", value)

            return self

        def discover(self, module_name: str):
            """Load module from a file"""
            lamp_post = self.branch(module_name)
            data = {}
            for key in lamp_post.scan():
                key = key.split(".")[0]
                i = key
                match key[0]:
                    case "i":
                        key = int(key[1:])
                    case "f":
                        key = float(key[1:])
                    case "b":
                        key = bool(key[1:])
                    case _:
                        key = str(key)
                data[key] = lamp_post.locate(i)
            return data

        def reflect(self, name: str, replacing: dict, remember: SaveType = None):
            """Update data in a file"""
            data = self.locate(name)

            if remember != None:
                replacing = parse_save_type(name, replacing, remember)

            if data is None:
                cprint(f"Can not reflect on the path, {name} is not found.", "red")
                return

            replacing.update(data)
            return replacing

        def reconstruct(
            self, module_name: str, replacing: dict, remember: SaveType = None
        ):
            """Update module in a file"""
            data = self.discover(module_name)

            if remember != None:
                replacing = parse_save_type(module_name, replacing, remember)

            if data is None:
                cprint(
                    f"Can not reconstruct the module, {module_name} is not found.",
                    "red",
                )
                return

            replacing.update(data)
            return replacing

        def dim(self, name: str):
            """Delete a file"""
            os.remove(f"{self.home}/{name}.p")
            return self

        def extinguish(self):
            """Delete the home folder"""
            if can_delete_folder(self.home):
                shutil.rmtree(self.home)
                del self
            else:
                cprint(
                    "Can not extinguish the light house, it's not empty and contains non lost files",
                    "red",
                )
                return self

    # Manager tailored layer for the Beacon class
    def save(key, inner=False, module=False):
        """Illuminate/Guide data to a file"""
        if inner is False and module is False:
            inner = "value"
        B = sonata.beacon
        if not module:
            if inner:
                B.branch(key).guide(inner, sonata.memory[key][inner])
            else:
                B.guide(key, sonata.memory[key])
        else:
            if inner:
                B.branch(key).illuminate(inner, sonata.memory[key][inner])
            else:
                B.illuminate(key, sonata.memory[key])
        return B

    def load(key, inner=False, module=False):
        """Discover/Locate data from a file"""
        B = sonata.beacon
        if inner is False and module is False:
            inner = "value"
        if not module:
            if inner:
                return B.branch(key).locate(inner)
            return B.locate(key)
        else:
            if inner:
                return B.branch(key).discover(inner)
            return B.discover(key)

    def recover(key, inner=False, module=False):
        """Reconstruct/Reflect data from a file"""
        B = sonata.beacon
        if inner is False and module is False:
            inner = "value"
        if not module:
            if inner:
                return B.branch(key).reflect(inner, sonata.memory[key][inner])
            return B.reflect(key, sonata.memory[key])
        else:
            if inner:
                return B.branch(key).reconstruct(inner, sonata.memory[key][inner])
            return B.reconstruct(key, sonata.memory[key])

    sonata.save = save
    sonata.load = load
    sonata.reload = recover

    return Beacon
