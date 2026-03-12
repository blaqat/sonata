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
    settings,
)
from modules.AI_manager import AI_Manager
from modules.policy_api import get_or_create_policy_api
from typing import Literal

import pickle
import os
import re
import shutil
from cryptography.fernet import Fernet

CONTEXT, MANAGER, PROMPT_MANAGER = AI_Manager.init(lazy=True)
__plugin_name__ = "beacon"
dir_path = os.path.dirname(os.path.realpath(__file__))

SaveType = Literal["m", "c", None]
GLOBAL_POLICY_SCOPE_ID = "__global__"


def can_delete_folder(folder_path):
    """Check if a folder is empty or contains only .p files"""
    # Check if the folder is empty or contains .p files
    for _, dirs, files in os.walk(folder_path):
        if not files and not dirs:
            return True
        for file in files:
            if file.endswith(".p"):
                return True
    return False


@MANAGER.builder
def beacon(sonata: AI_Manager):
    """Beacon plugin for saving and loading data to/from files"""

    def parse_save_type(name, d, t):
        """Parse the save type and return the appropriate data"""
        if t == "m":
            if type(d) == dict:
                return sonata.get(name, **d)
            elif type(d) == list or type(d) == tuple:
                return sonata.get(name, *d)
            elif type(d) == str:
                return sonata.get(name, d)
            else:
                return sonata.get(name)
        elif t == "c":
            return sonata.config.get(name)
        return None

    class Beacon:
        home: str  # The home folder where things are saved
        key: bytes | None

        def __init__(self, path: str = "beacon-mainland", key: bytes | None = None):
            """Initialize the Beacon with a home folder and optional encryption key"""
            self.key = key
            self.policy_api = get_or_create_policy_api(sonata)
            if not self.policy_api.has_namespace("beacon"):
                self.policy_api.register_namespace("beacon", plugin=True)
            self.light_house(path, True)

        def _normalize_policy_path(self, path: str) -> str:
            normalized = str(path or "").strip().replace("\\", "/")
            normalized = re.sub(r"/+", "/", normalized)
            normalized = normalized.strip("/").lower()
            return normalized

        def _path_action(self, path: str) -> str:
            normalized_path = self._normalize_policy_path(path)
            return f"beacon.encrypt.path.{normalized_path}"

        def _resolve_encryption(
            self, encrypted: bool, encrypted_path: str | None
        ) -> bool:
            if encrypted_path is None:
                return bool(encrypted)
            action = self._path_action(encrypted_path)
            return self.policy_api.evaluate(
                "beacon",
                action,
                guild_id=GLOBAL_POLICY_SCOPE_ID,
                default=bool(encrypted),
            )

        def _get_fernet(self):
            if not self.key:
                # If no key is provided, we try to get one from the environment or config
                # As a fallback, this will raise an error if encryption is requested but no key exists
                key = settings.BEACON_ENCRYPTION_KEY
                if key:
                    self.key = key.encode() if isinstance(key, str) else key

            if not self.key:
                raise ValueError(
                    "Encryption requested but no encryption key is set. Please set the BEACON_ENCRYPTION_KEY environment variable or pass a key to Beacon."
                )
            return Fernet(self.key)

        def island(self, path: str, home=False):
            """Set the home folder"""
            l = Beacon(key=self.key)
            l.light_house(path, home)
            return l

        def branch(self, path: str):
            """Create a new folder"""
            return self.island(f"{self.home}/{path}")

        def light_house(self, path: str, home=False):
            """Set the home folder"""
            self.home = (f"{dir_path}/" if home else "") + path
            if not os.path.exists(self.home):
                os.makedirs(self.home, exist_ok=True)
            return self

        def scan(self):
            """List all the files in the home folder"""
            return os.listdir(self.home)

        def guide(
            self,
            name: str,
            data: any = None,
            remember: SaveType = None,
            encrypted: bool = False,
            encrypted_path: str | None = None,
        ):
            """Save data to a file"""
            if remember != None:
                data = parse_save_type(name, data, remember)

            if data is None:
                cprint(f"Can not light up the path, {name} is not found.", "red")
                return

            with open(f"{self.home}/{name}.p", "wb") as f:
                pickled_data = pickle.dumps(data)
                should_encrypt = self._resolve_encryption(
                    encrypted,
                    encrypted_path or f"{self.home}/{name}",
                )
                if should_encrypt:
                    fernet = self._get_fernet()
                    pickled_data = fernet.encrypt(pickled_data)
                f.write(pickled_data)

            return self

        def illuminate(
            self,
            module_name: str,
            data: dict,
            remember: SaveType = None,
            encrypted: bool = False,
            encrypted_path: str | None = None,
        ):
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

                path = encrypted_path or f"{self.home}/{module_name}/{t}{key}"
                lamp_post.guide(
                    f"{t}{key}",
                    value,
                    encrypted=encrypted,
                    encrypted_path=path,
                )

            return self

        def locate(
            self,
            name: str,
            encrypted: bool = False,
            encrypted_path: str | None = None,
        ):
            """Load data from a file"""
            try:
                with open(f"{self.home}/{name}.p", "rb") as f:
                    data = f.read()
                    should_encrypt = self._resolve_encryption(
                        encrypted,
                        encrypted_path or f"{self.home}/{name}",
                    )
                    if should_encrypt:
                        fernet = self._get_fernet()
                        data = fernet.decrypt(data)
                    return pickle.loads(data)
            except:
                cprint(
                    f"Can not locate the path, {name} is not found or could not be decrypted.",
                    "red",
                )
                return

        def discover(
            self,
            module_name: str,
            encrypted: bool = False,
            encrypted_path: str | None = None,
        ):
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
                    case "s":
                        key = str(key[1:])
                path = encrypted_path or f"{self.home}/{module_name}/{i}"
                data[key] = lamp_post.locate(
                    i,
                    encrypted=encrypted,
                    encrypted_path=path,
                )
            return data

        def reflect(
            self,
            name: str,
            replacing: dict,
            remember: SaveType = None,
            encrypted: bool = False,
        ):
            """Update data in a file"""
            data = self.locate(name, encrypted=encrypted)

            if remember != None:
                replacing = parse_save_type(name, replacing, remember)

            if data is None:
                cprint(f"Can not reflect on the path, {name} is not found.", "red")
                return

            replacing.update(data)
            return replacing

        def reconstruct(
            self,
            module_name: str,
            replacing: dict,
            remember: SaveType = None,
            encrypted: bool = False,
        ):
            """Update module in a file"""
            data = self.discover(module_name, encrypted=encrypted)

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

        def darken(self, module_name: str = None):
            """Delete all files in a island"""
            lamp_post = self
            if module_name is None:
                lamp_post = self.branch(module_name)
            for file in lamp_post.scan():
                lamp_post.dim(file.split(".")[0])
            return self

        def extinguish(self):
            """Puts out the light in the light house"""
            if can_delete_folder(self.home):
                shutil.rmtree(self.home)
            else:
                cprint(
                    "Can not extinguish the light house, it's not empty and contains non lost files",
                    "red",
                )
            return self

        def flash(self, save=True, encrypted: bool = False):
            """Temporary Clone the beacon files"""

            dir = self.home.replace(dir_path + "/beacon-mainland", "mainland")
            dir = dir.replace(dir_path, "home")
            flash = self.island(f"beacon-flashes", home=True).branch(dir)

            if save:
                for file in self.scan():
                    # Locate the data then guide it to the flash
                    if os.path.isdir(f"{self.home}/{file}"):
                        data = self.discover(file, encrypted=encrypted)
                        flash.illuminate(file, data, encrypted=encrypted)
                    else:
                        data = self.locate(file.split(".")[0], encrypted=encrypted)
                        flash.guide(file.split(".")[0], data, encrypted=encrypted)

            return flash

        def absorb(self, flash=None, extinguish=True, encrypted: bool = False):
            """Absorb the flash files"""
            if flash is None:
                dir = self.home.replace(dir_path + "/beacon-mainland", "mainland")
                dir = dir.replace(dir_path, "home")
                flash = self.island(f"beacon-flashes", home=True).branch(dir)
            for file in flash.scan():
                if os.path.isdir(f"{flash.home}/{file}"):
                    data = flash.discover(file, encrypted=encrypted)
                    self.illuminate(file, data, encrypted=encrypted)
                else:
                    data = flash.locate(file.split(".")[0], encrypted=encrypted)
                    self.guide(file.split(".")[0], data, encrypted=encrypted)

            if extinguish:
                flash.extinguish()

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
