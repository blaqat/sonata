"""Characterization tests for Discord effect ORDER on Cursor entry paths (SONA-105 Phase 4.0)."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.access import AccessController, ImageRetentionStore, MemoryAccessStore
from cursor_cloud.config import load_cursor_config
from cursor_cloud.models import (
    AgentSession,
    PendingDecision,
    RunRequestEnvelope,
    RunStatus,
    ScopeKey,
    utcnow,
)
from cursor_cloud.session_store import MemorySessionStore
from cursor_cloud.thread_renderer import THREAD_THINKING_INDICATOR

GOD = "100000000000000001"
T1 = "100000000000000002"
T2 = "100000000000000003"


def load_cursor_plugin():
    import importlib

    from modules.AI_manager import AI_Manager

    pkg = "modules.plugins.cursor-commands"
    previous = AI_Manager.M.MANAGER
    try:
        for key in list(sys.modules):
            if key == pkg or key.startswith(pkg + "."):
                del sys.modules[key]
        mod = importlib.import_module(pkg + ".module")
        mod.discord_ui = sys.modules[pkg + ".discord_ui"]
        mod.workflows = sys.modules[pkg + ".workflows"]
        mod.runtime = sys.modules[pkg + ".runtime"]
        return mod
    finally:
        AI_Manager.M.MANAGER = previous


@contextmanager
def patch_cursor(mod, name, *args, **kwargs):
    """Patch ``name`` on the plugin module and owning package submodules.

    Yields the mock/object from the primary (plugin module) patch when present,
    matching ``patch.object`` ``as`` semantics.
    """
    from contextlib import ExitStack
    from unittest.mock import patch

    targets = []
    for m in (
        mod,
        getattr(mod, "discord_ui", None),
        getattr(mod, "workflows", None),
        getattr(mod, "runtime", None),
    ):
        if m is not None and hasattr(m, name):
            targets.append(m)
    with ExitStack() as stack:
        primary = None
        for i, m in enumerate(targets):
            cm = patch.object(m, name, *args, **kwargs)
            val = stack.enter_context(cm)
            if i == 0:
                primary = val
        yield primary





class PermissivePolicy:
    def can_speak(self, **kwargs):
        return True

    def is_command_allowed(self, **kwargs):
        return True


class ParentAllowsChildDeniesPolicy:
    def can_speak(self, *, guild_id, channel_id, user_id, role_ids):
        return str(channel_id) == "100"

    def is_command_allowed(self, *, guild_id, channel_id, command, user_id, role_ids):
        return str(channel_id) == "100"


def _make_client():
    client = MagicMock()
    client.create_agent = AsyncMock(
        return_value=(
            SimpleNamespace(id="bc-new", name="n", model="m"),
            SimpleNamespace(id="run-new", status=RunStatus.CREATING),
        )
    )
    client.create_run = AsyncMock(
        return_value=SimpleNamespace(id="run-f", status=RunStatus.CREATING)
    )
    client.cancel_run = AsyncMock()
    client.get_run = AsyncMock(
        return_value=SimpleNamespace(
            id="run-1", status=RunStatus.RUNNING, result=None, duration_ms=None, git=None
        )
    )
    client.aclose = AsyncMock()
    return client


def _bootstrap(mod):
    cfg = load_cursor_config(
        {
            "enabled": True,
            "default_repository_url": "https://github.com/o/r",
            "session_idle_prompt_minutes": 10,
            "access": {"tier1_user_ids": [T1], "tier2_user_ids": [T2]},
        },
        env={"CURSOR_API_KEY": "k", "GOD": GOD},
    )
    sessions = MemorySessionStore()
    store = MemoryAccessStore()
    access = AccessController(
        cfg, store, image_retention=ImageRetentionStore(max_total_bytes=5_000_000)
    )
    client = _make_client()
    mod.reset_runtime(
        config=cfg,
        sessions=sessions,
        access_store=store,
        access=access,
        client=client,
        cdn=MagicMock(aclose=AsyncMock()),
        bot=MagicMock(add_view=MagicMock()),
        trackers={},
        policy_manager=PermissivePolicy(),
        require_policy=False,
    )
    return sessions, access, cfg, client


def _interaction(user_id, *, guild_id=1, channel_id=2):
    user = SimpleNamespace(
        id=int(user_id),
        roles=[],
        display_name="User",
        name="user",
    )
    response = MagicMock()
    response._done = False

    def is_done():
        return response._done

    response.is_done = is_done

    async def defer(**kwargs):
        response._done = True

    response.defer = AsyncMock(side_effect=defer)
    response.send_message = AsyncMock(
        side_effect=lambda *a, **k: setattr(response, "_done", True)
    )
    status_message = SimpleNamespace(
        id=9001,
        channel=SimpleNamespace(id=channel_id),
        edit=AsyncMock(),
        delete=AsyncMock(),
    )
    followup = MagicMock()
    followup.send = AsyncMock(return_value=status_message)
    channel = MagicMock()
    channel.id = channel_id
    posted = []

    async def send(content, **kwargs):
        msg = SimpleNamespace(
            id=1000 + len(posted),
            channel=SimpleNamespace(id=channel_id),
            content=content,
            edit=AsyncMock(),
            delete=AsyncMock(),
        )
        posted.append(msg)
        return msg

    channel.send = AsyncMock(side_effect=send)
    channel.create_thread = AsyncMock()
    guild = MagicMock()
    guild.get_channel.return_value = channel
    guild.get_member.return_value = None
    interaction = SimpleNamespace(
        user=user,
        guild_id=guild_id,
        channel_id=channel_id,
        channel=channel,
        guild=guild,
        client=SimpleNamespace(sonata=None, fetch_channel=AsyncMock(return_value=channel)),
        response=response,
        followup=followup,
        message=None,
        data={},
        id=123,
        _posted=posted,
    )
    return interaction


class FakeTracker:
    def __init__(self, *args, **kwargs):
        pass

    async def track(self, *args, **kwargs):
        return SimpleNamespace(status=RunStatus.FINISHED, degraded=False)


def assert_subsequence(log, expected):
    idx = 0
    for effect in log:
        if idx < len(expected) and effect == expected[idx]:
            idx += 1
    if idx != len(expected):
        raise AssertionError(
            f"expected subsequence {expected}, got {log} (matched {idx}/{len(expected)})"
        )


def _is_approval_card(content, kwargs):
    return kwargs.get("view") is not None or "Cursor approval" in str(content)


def _is_status_post(content):
    text = str(content)
    return (
        THREAD_THINKING_INDICATOR in text
        or "thinking" in text
        or "Queued" in text
        or text.startswith("### ")
    )


def instrument_channel_send(channel, log):
    orig_send = channel.send

    async def send(content, **kwargs):
        if _is_approval_card(content, kwargs):
            log.append("card_post")
        elif _is_status_post(content):
            log.append("status_post")
        return await orig_send(content, **kwargs)

    channel.send = AsyncMock(side_effect=send)


def instrument_thread_send(thread, log):
    orig_send = thread.send

    async def send(content, **kwargs):
        if _is_status_post(content):
            log.append("status_post")
        msg = await orig_send(content, **kwargs)
        if getattr(msg, "channel", None) is None:
            msg.channel = thread
        return msg

    thread.send = AsyncMock(side_effect=send)


def instrument_message_edit(message, log):
    orig_edit = message.edit

    async def edit(*args, **kwargs):
        content = kwargs.get("content")
        if content is None and args:
            content = args[0]
        if _is_status_post(content):
            log.append("status_post")
        return await orig_edit(*args, **kwargs)

    message.edit = AsyncMock(side_effect=edit)


@contextmanager
def record_effects(mod, interaction=None, *, extra_channels=()):
    log = []
    orig_defer = mod._defer
    orig_ephemeral = mod._ephemeral
    orig_public = mod._public
    orig_ui_notify = mod.InteractionUI.notify
    orig_ui_post = mod.InteractionUI.post_status

    async def defer(inter, *, ephemeral=True):
        log.append("defer")
        await orig_defer(inter, ephemeral=ephemeral)
        if hasattr(inter.response, "_done"):
            inter.response._done = True

    async def ephemeral(inter, content):
        log.append("ephemeral_ack")
        await orig_ephemeral(inter, content)

    async def public(inter, content, **kwargs):
        log.append("status_post")
        return await orig_public(inter, content, **kwargs)

    async def ui_notify(self, text):
        log.append("ephemeral_ack")
        return await orig_ui_notify(self, text)

    async def ui_post(self, content, **kwargs):
        log.append("status_post")
        return await orig_ui_post(self, content, **kwargs)

    channels = []
    if interaction is not None and getattr(interaction, "channel", None) is not None:
        channels.append(interaction.channel)
    channels.extend(extra_channels)
    for ch in channels:
        if ch is not None and hasattr(ch, "send"):
            instrument_channel_send(ch, log)

    with (
        patch_cursor(mod, "_defer", new=defer),
        patch_cursor(mod, "_ephemeral", new=ephemeral),
        patch_cursor(mod, "_public", new=public),
        patch.object(mod.InteractionUI, "notify", new=ui_notify),
        patch.object(mod.InteractionUI, "post_status", new=ui_post),
        patch_cursor(mod, "RunTracker", FakeTracker),
    ):
        yield log


class TestCursorEffectOrder(unittest.IsolatedAsyncioTestCase):
    async def test_slash_run_t1_launch_order(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        interaction = _interaction(T1)
        ctx = SimpleNamespace(interaction=interaction)
        with record_effects(mod, interaction) as log:
            with patch_cursor(mod,
                "_build_context_for_run",
                new=AsyncMock(return_value=("do thing", [], [])),
            ):
                await mod.cursor_run(
                    ctx,
                    prompt="do thing",
                    message=None,
                    image1=None,
                    image2=None,
                    image3=None,
                    image4=None,
                    image5=None,
                )
        assert_subsequence(log, ["defer", "status_post"])

    async def test_slash_run_t2_approval_order(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        interaction = _interaction(T2)
        ctx = SimpleNamespace(interaction=interaction)
        with record_effects(mod, interaction) as log:
            with patch_cursor(mod,
                "_build_context_for_run",
                new=AsyncMock(return_value=("needs approval", [], [])),
            ):
                await mod.cursor_run(
                    ctx,
                    prompt="needs approval",
                    message=None,
                    image1=None,
                    image2=None,
                    image3=None,
                    image4=None,
                    image5=None,
                )
        assert_subsequence(log, ["defer", "ephemeral_ack", "card_post"])

    async def test_cursor_new_t1_launch_order(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        interaction = _interaction(T1)
        thread = MagicMock()
        thread.id = 888
        thread.mention = "<#888>"
        activity = SimpleNamespace(id=501, channel=thread, edit=AsyncMock(), delete=AsyncMock())
        thread.send = AsyncMock(return_value=activity)
        interaction.channel.create_thread = AsyncMock(return_value=thread)
        ctx = SimpleNamespace(interaction=interaction)
        with record_effects(mod, interaction) as log:
            instrument_thread_send(thread, log)
            with patch_cursor(mod, "_generate_session_title", new=AsyncMock(return_value="session")):
                with patch_cursor(mod,
                    "_build_context_for_run",
                    new=AsyncMock(return_value=("hello thread", [], [])),
                ):
                    with patch_cursor(mod, "_channel_is_thread", return_value=False):
                        await mod.cursor_new(
                            ctx,
                            prompt="hello thread",
                            message=None,
                            image1=None,
                            image2=None,
                            image3=None,
                            image4=None,
                            image5=None,
                        )
        assert_subsequence(log, ["defer", "status_post", "ephemeral_ack"])

    async def test_agent_prefix_order(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier1_user_ids": [T1], "tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        mod.reset_runtime(
            config=cfg,
            sessions=MemorySessionStore(),
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(add_view=MagicMock()),
            client=_make_client(),
        )
        message = MagicMock()
        message.id = 42
        message.content = "$agent fix the flaky test"
        message.attachments = []
        message.author = SimpleNamespace(
            id=int(T1), roles=[], display_name="Tier1", name="tier1"
        )
        message.guild = SimpleNamespace(id=1)
        message.channel = SimpleNamespace(id=100, send=AsyncMock())
        message.reply = AsyncMock()
        ctx = SimpleNamespace(
            message=message,
            author=message.author,
            guild=message.guild,
            channel=message.channel,
        )
        thread = MagicMock()
        thread.id = 999
        thread.mention = "<#999>"
        activity = SimpleNamespace(id=601, channel=thread, edit=AsyncMock(), delete=AsyncMock())
        thread.send = AsyncMock(return_value=activity)
        with patch_cursor(mod, "_generate_session_title", new=AsyncMock(return_value="fix flaky")):
            with patch_cursor(mod,
                "_build_context_from_message",
                new=AsyncMock(return_value=("fix the flaky test", [], [])),
            ):
                with patch_cursor(mod, "_channel_is_thread", return_value=False):
                    with record_effects(mod) as log:
                        instrument_thread_send(thread, log)
                        with patch_cursor(mod,
                            "_create_public_agent_thread",
                            new=AsyncMock(return_value=thread),
                        ):
                            await mod.handle_agent_prefix(ctx, "fix the flaky test")
        self.assertEqual(log, ["status_post"])
        self.assertNotIn("defer", log)
        self.assertNotIn("ephemeral_ack", log)

    async def test_thread_followup_order(self):
        mod = load_cursor_plugin()
        cfg = load_cursor_config(
            {
                "enabled": True,
                "default_repository_url": "https://github.com/o/r",
                "access": {"tier1_user_ids": [GOD], "tier2_user_ids": [T2]},
            },
            env={"CURSOR_API_KEY": "k", "GOD": GOD},
        )
        sessions = MemorySessionStore()
        scope = ScopeKey("1", "200", T2)
        session = AgentSession(
            scope=scope,
            agent_id="bc-1",
            owner_id=T2,
            thread_bound=True,
            parent_channel_id="100",
            status_channel_id="200",
            status_message_id="55",
            latest_run_status=RunStatus.FINISHED,
            active=True,
        )
        await sessions.upsert(session)
        await sessions.set_active(scope, "bc-1")
        mod.reset_runtime(
            config=cfg,
            sessions=sessions,
            access=AccessController(
                cfg,
                MemoryAccessStore(),
                image_retention=ImageRetentionStore(max_total_bytes=1),
            ),
            policy_manager=ParentAllowsChildDeniesPolicy(),
            require_policy=True,
            bot=MagicMock(add_view=MagicMock()),
            client=_make_client(),
        )
        activity = MagicMock()
        activity.id = 55
        activity.content = "### Activity\n- `grep` (running)"
        channel = MagicMock()
        channel.id = 200
        channel.parent_id = 100
        channel.fetch_message = AsyncMock(return_value=activity)
        channel.send = AsyncMock()
        message = SimpleNamespace(
            id=901,
            author=SimpleNamespace(id=int(T2), bot=False, roles=[]),
            content="follow up please",
            attachments=[],
            reference=None,
            channel=channel,
            guild=SimpleNamespace(id=1),
        )
        with patch_cursor(mod, "_channel_is_thread", return_value=True):
            with record_effects(mod) as log:
                instrument_message_edit(activity, log)
                await mod.handle_thread_message(message)
        self.assertEqual(log, ["status_post"])
        self.assertNotIn("defer", log)

    async def test_approve_launch_order(self):
        mod = load_cursor_plugin()
        _bootstrap(mod)
        scope = ScopeKey("1", "2", T2)
        env = RunRequestEnvelope(
            requester_id=T2,
            scope=scope,
            prompt_text="approved prompt",
            model="m",
            repository_url="https://github.com/o/r",
            starting_ref="main",
            agent_id=None,
            is_follow_up=False,
        )
        req = await mod.get_runtime().access.create_approval_request(
            env, prompt_preview="approved prompt"
        )
        interaction = _interaction(GOD)
        interaction.data = {"custom_id": f"c105:apr_once:{req.request_id}"}
        with record_effects(mod, interaction) as log:
            ok = await mod.handle_component(interaction)
        self.assertTrue(ok)
        assert_subsequence(log, ["defer", "status_post"])

    async def test_decision_resume_idle_continue_order(self):
        mod = load_cursor_plugin()
        sessions, access, cfg, client = _bootstrap(mod)
        scope = ScopeKey("1", "2", T1)
        await sessions.upsert(
            AgentSession(
                scope=scope,
                agent_id="a1",
                owner_id=T1,
                active=True,
                latest_run_id="r0",
                latest_run_status=RunStatus.FINISHED,
            )
        )
        await sessions.save_decision(
            PendingDecision(
                decision_id="idle_resume",
                scope=scope,
                agent_id="a1",
                kind="idle",
                expires_at=utcnow() + timedelta(minutes=5),
            )
        )
        await sessions.save_pending_payload(
            "idle_resume",
            {
                "prompt_text": "built prompt",
                "prompt": "continue please",
                "skipped": [],
                "image_metas": [],
            },
        )
        interaction = _interaction(T1)
        interaction.data = {"custom_id": "c105:idle_cont:idle_resume"}
        with record_effects(mod, interaction) as log:
            ok = await mod.handle_component(interaction)
        self.assertTrue(ok)
        assert_subsequence(log, ["defer", "ephemeral_ack", "status_post"])


if __name__ == "__main__":
    unittest.main()
