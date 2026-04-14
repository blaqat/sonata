import importlib.util
import pathlib
import pickle
import shutil
import sys
import types
import unittest
import uuid


def _load_beacon_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    module_path = src_root / "modules" / "plugins" / "beacon.py"
    spec = importlib.util.spec_from_file_location("beacon_plugin", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load beacon module spec")

    utils_stub = types.ModuleType("modules.utils")
    utils_stub.async_cprint = lambda *_, **__: None
    utils_stub.settings = types.SimpleNamespace(BEACON_ENCRYPTION_KEY=None)

    class _ManagerStub:
        @staticmethod
        def builder(func):
            return func

    class _AIManagerStub:
        @staticmethod
        def init(*_, **__):
            return None, _ManagerStub(), None

    ai_manager_stub = types.ModuleType("modules.AI_manager")
    ai_manager_stub.AI_Manager = _AIManagerStub

    class _FernetStub:
        def __init__(self, _key):
            pass

        @staticmethod
        def generate_key():
            return b"test-key"

        def encrypt(self, payload):
            return b"enc:" + payload

        def decrypt(self, payload):
            if not payload.startswith(b"enc:"):
                raise ValueError("payload not encrypted")
            return payload[4:]

    cryptography_stub = types.ModuleType("cryptography")
    cryptography_fernet_stub = types.ModuleType("cryptography.fernet")
    cryptography_fernet_stub.Fernet = _FernetStub

    original_utils = sys.modules.get("modules.utils")
    original_ai_manager = sys.modules.get("modules.AI_manager")
    original_cryptography = sys.modules.get("cryptography")
    original_cryptography_fernet = sys.modules.get("cryptography.fernet")
    sys.modules["modules.utils"] = utils_stub
    sys.modules["modules.AI_manager"] = ai_manager_stub
    sys.modules["cryptography"] = cryptography_stub
    sys.modules["cryptography.fernet"] = cryptography_fernet_stub
    try:
        module = importlib.util.module_from_spec(spec)
        sys.modules["beacon_plugin"] = module
        spec.loader.exec_module(module)
    finally:
        if original_utils is None:
            sys.modules.pop("modules.utils", None)
        else:
            sys.modules["modules.utils"] = original_utils
        if original_ai_manager is None:
            sys.modules.pop("modules.AI_manager", None)
        else:
            sys.modules["modules.AI_manager"] = original_ai_manager
        if original_cryptography is None:
            sys.modules.pop("cryptography", None)
        else:
            sys.modules["cryptography"] = original_cryptography
        if original_cryptography_fernet is None:
            sys.modules.pop("cryptography.fernet", None)
        else:
            sys.modules["cryptography.fernet"] = original_cryptography_fernet

    return module


class _FakeConfig:
    def get(self, *_args, **_kwargs):
        return None


class _FakeSonata:
    def __init__(self):
        self.config = _FakeConfig()


class BeaconPolicyTests(unittest.TestCase):
    def setUp(self):
        self.beacon_module = _load_beacon_module()
        self.sonata = _FakeSonata()
        beacon_class = self.beacon_module.beacon(self.sonata)
        self.folder_name = f"beacon-policy-test-{uuid.uuid4().hex}"
        self.beacon = beacon_class(path=self.folder_name, key=b"test-key")

    def tearDown(self):
        shutil.rmtree(self.beacon.home, ignore_errors=True)

    def test_explicit_path_policy_match_encrypts_and_round_trips(self):
        action = self.beacon._path_action(f"{self.beacon.home}/secret")
        self.beacon.policy_api.set_rule(
            "beacon",
            "guild",
            self.beacon_module.GLOBAL_POLICY_SCOPE_ID,
            action,
            "allow",
        )

        payload = {"message": "hello"}
        self.beacon.guide("secret", payload, encrypted=False)
        loaded = self.beacon.locate("secret", encrypted=False)
        self.assertEqual(loaded, payload)

    def test_non_match_falls_back_to_default_flag(self):
        plain_payload = {"value": 1}
        self.beacon.guide("plain", plain_payload, encrypted=False)
        with open(f"{self.beacon.home}/plain.p", "rb") as handle:
            raw_plain = handle.read()
        self.assertEqual(pickle.loads(raw_plain), plain_payload)

        encrypted_payload = {"value": 2}
        self.beacon.guide("secure", encrypted_payload, encrypted=True)
        with open(f"{self.beacon.home}/secure.p", "rb") as handle:
            raw_encrypted = handle.read()
        with self.assertRaises(Exception):
            pickle.loads(raw_encrypted)
        self.assertEqual(
            self.beacon.locate("secure", encrypted=True), encrypted_payload
        )

    def test_path_normalization_is_case_and_separator_stable(self):
        action = self.beacon._path_action(f"{self.beacon.home}\\NESTED/PATH")
        self.beacon.policy_api.set_rule(
            "beacon",
            "guild",
            self.beacon_module.GLOBAL_POLICY_SCOPE_ID,
            action,
            "allow",
        )

        payload = {"ok": True}
        self.beacon.guide(
            "norm",
            payload,
            encrypted=False,
            encrypted_path=f"{self.beacon.home}/nested/path",
        )
        self.assertEqual(
            self.beacon.locate(
                "norm",
                encrypted=False,
                encrypted_path=f"{self.beacon.home}\\NESTED/PATH",
            ),
            payload,
        )

    def test_beacon_reactivates_namespace_on_reuse(self):
        action = self.beacon._path_action(f"{self.beacon.home}/secret")
        self.beacon.policy_api.set_rule(
            "beacon",
            "guild",
            self.beacon_module.GLOBAL_POLICY_SCOPE_ID,
            action,
            "allow",
        )
        self.beacon.policy_api.unload_namespace("beacon")

        beacon_class = self.beacon_module.beacon(self.sonata)
        second_folder = f"beacon-policy-test-{uuid.uuid4().hex}"
        reloaded = beacon_class(path=second_folder, key=b"test-key")
        self.addCleanup(shutil.rmtree, reloaded.home, True)

        self.assertTrue(
            reloaded._resolve_encryption(
                False,
                f"{self.beacon.home}/secret",
            )
        )

    def test_chat_channel_path_rule_encrypts_saved_history(self):
        action = self.beacon._path_action(f"{self.beacon.home}/chat/value/i123")
        self.beacon.policy_api.set_rule(
            "beacon",
            "guild",
            self.beacon_module.GLOBAL_POLICY_SCOPE_ID,
            action,
            "allow",
        )

        payload = {123: [("User", "alice", "hello", None)]}
        self.beacon.branch("chat").illuminate("value", payload, encrypted=False)

        with open(f"{self.beacon.home}/chat/value/i123.p", "rb") as handle:
            raw_encrypted = handle.read()

        with self.assertRaises(Exception):
            pickle.loads(raw_encrypted)

        loaded = self.beacon.branch("chat").discover("value", encrypted=False)
        self.assertEqual(loaded, payload)


if __name__ == "__main__":
    unittest.main()
