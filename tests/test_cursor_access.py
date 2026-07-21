import pathlib
import sys
import unittest
from datetime import timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cursor_cloud.access import (
    AccessController,
    MemoryAccessStore,
    ImageRetentionStore,
    envelope_hash,
)
from cursor_cloud.config import load_cursor_config
from cursor_cloud.errors import (
    AuthorizationError,
    GrantConsumedError,
    StaleStateError,
    ValidationError,
)
from cursor_cloud.models import (
    AccessTier,
    ApprovalDecision,
    ImageInput,
    RunRequestEnvelope,
    ScopeKey,
    utcnow,
)


GOD = "100000000000000001"
T1 = "100000000000000002"
T2 = "100000000000000003"
OTHER = "100000000000000004"


def make_controller(overlay=None, file_t1=None, file_t2=None, god=GOD):
    env = {"CURSOR_API_KEY": "k", "GOD": god or ""}
    cfg = load_cursor_config(
        {
            "enabled": True,
            "default_repository_url": "https://github.com/o/r",
            "access": {
                "tier1_user_ids": file_t1 or [],
                "tier2_user_ids": file_t2 or [],
                "default_grant_minutes": 10,
                "approval_timeout_hours": 12,
            },
        },
        env=env,
    )
    store = MemoryAccessStore()
    ctrl = AccessController(cfg, store, image_retention=ImageRetentionStore(max_total_bytes=10_000_000))
    return ctrl, store


def envelope(user=T2, prompt="p", agent=None, follow=False):
    return RunRequestEnvelope(
        requester_id=user,
        scope=ScopeKey("g1", "c1", user),
        prompt_text=prompt,
        model="m1",
        repository_url="https://github.com/o/r",
        starting_ref="main",
        agent_id=agent,
        is_follow_up=follow,
        image_metas=[],
    )


class TestTiers(unittest.IsolatedAsyncioTestCase):
    async def test_god_immutable_and_fail_closed(self):
        ctrl, _ = make_controller()
        self.assertEqual(await ctrl.resolve_tier(GOD), AccessTier.GOD)
        ctrl2, _ = make_controller(god="")
        self.assertEqual(await ctrl2.resolve_tier(GOD), AccessTier.DENIED)
        self.assertEqual(await ctrl2.resolve_tier(T1), AccessTier.DENIED)

    async def test_overlay_precedence_and_reset(self):
        ctrl, store = make_controller(file_t2=[T2])
        self.assertEqual(await ctrl.resolve_tier(T2), AccessTier.APPROVAL)
        await ctrl.set_user_tier(GOD, T2, 1)
        self.assertEqual(await ctrl.resolve_tier(T2), AccessTier.ADMIN)
        await ctrl.set_user_tier(GOD, T2, "reset")
        self.assertEqual(await ctrl.resolve_tier(T2), AccessTier.APPROVAL)
        await ctrl.set_user_tier(GOD, T2, 3)
        self.assertEqual(await ctrl.resolve_tier(T2), AccessTier.DENIED)

    async def test_god_only_management(self):
        ctrl, _ = make_controller()
        with self.assertRaises(AuthorizationError):
            await ctrl.set_user_tier(T1, OTHER, 1)
        with self.assertRaises(ValidationError):
            await ctrl.set_user_tier(GOD, GOD, 1)

    async def test_tier1_can_approve_not_configure(self):
        ctrl, _ = make_controller()
        await ctrl.set_user_tier(GOD, T1, 1)
        self.assertEqual(await ctrl.require_approver(T1), AccessTier.ADMIN)
        with self.assertRaises(AuthorizationError):
            await ctrl.require_god(T1)

    async def test_tier3_denied(self):
        ctrl, _ = make_controller()
        self.assertEqual(await ctrl.resolve_tier(OTHER), AccessTier.DENIED)
        self.assertFalse(await ctrl.can_use_command(OTHER, "run"))
        self.assertFalse(await ctrl.can_use_command(OTHER, "status"))


class TestApprovals(unittest.IsolatedAsyncioTestCase):
    async def test_once_hash_bind_and_consume(self):
        ctrl, _ = make_controller()
        await ctrl.set_user_tier(GOD, T1, 1)
        env = envelope(prompt="exact")
        req = await ctrl.create_approval_request(env, prompt_preview="exact")
        await ctrl.decide_request(T1, req.request_id, mode="once")
        grant = await ctrl.find_valid_grant(env.scope, T2, env)
        self.assertIsNotNone(grant)
        # Changed prompt => no grant
        other = envelope(prompt="changed")
        self.assertIsNone(await ctrl.find_valid_grant(env.scope, T2, other))
        consumed = await ctrl.consume_grant_for_submit(grant, env)
        self.assertTrue(consumed.consumed)
        with self.assertRaises(StaleStateError):
            await ctrl.consume_grant_for_submit(grant, env)

    async def test_timed_default_and_custom(self):
        ctrl, _ = make_controller()
        env = envelope()
        req = await ctrl.create_approval_request(env, prompt_preview="p")
        decided = await ctrl.decide_request(GOD, req.request_id, mode="timed")
        self.assertEqual(decided.grant_minutes, 10)
        grant = await ctrl.store.get_grant(decided.grant_id)
        self.assertEqual(grant.kind, "timed")
        # Still valid for different prompt
        self.assertIsNotNone(await ctrl.find_valid_grant(env.scope, T2, envelope(prompt="other")))

        req2 = await ctrl.create_approval_request(envelope(prompt="x2"), prompt_preview="x2")
        decided2 = await ctrl.decide_request(GOD, req2.request_id, mode="timed", minutes=30)
        self.assertEqual(decided2.grant_minutes, 30)

    async def test_expiry_12h(self):
        ctrl, _ = make_controller()
        env = envelope()
        req = await ctrl.create_approval_request(env, prompt_preview="p")
        req.expires_at = utcnow() - timedelta(seconds=1)
        await ctrl.store.save_request(req)
        expired = await ctrl.expire_stale_requests()
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].decision, ApprovalDecision.EXPIRED)

    async def test_deny_and_stale_race(self):
        ctrl, _ = make_controller()
        env = envelope()
        req = await ctrl.create_approval_request(env, prompt_preview="p")
        await ctrl.decide_request(GOD, req.request_id, mode="deny")
        with self.assertRaises(StaleStateError):
            await ctrl.decide_request(GOD, req.request_id, mode="once")

    async def test_submit_failed_after_consume_fail_closed(self):
        ctrl, _ = make_controller()
        env = envelope()
        req = await ctrl.create_approval_request(
            env,
            prompt_preview="p",
            images=[ImageInput(mime_type="image/png", data_b64="aaaa", size_bytes=3)],
        )
        await ctrl.decide_request(GOD, req.request_id, mode="once")
        grant = await ctrl.find_valid_grant(env.scope, T2, env)
        await ctrl.consume_grant_for_submit(grant, env)
        await ctrl.mark_submit_failed_after_consume(grant)
        self.assertIsNone(await ctrl.images.get(req.request_id))
        # Cannot reuse
        self.assertIsNone(await ctrl.find_valid_grant(env.scope, T2, env))
        with self.assertRaises(GrantConsumedError):
            ctrl.raise_submit_failed(grant, RuntimeError("api down"))

    async def test_image_retention_bound(self):
        store = ImageRetentionStore(max_total_bytes=10)
        big = ImageInput(mime_type="image/png", data_b64="a" * 20, size_bytes=20)
        item = await store.put("r1", [big, ImageInput(mime_type="image/png", data_b64="bb", size_bytes=2)])
        # First image alone exceeds cap => retained may be empty or partial
        self.assertLessEqual(item.total_bytes, 10)

    async def test_audit_bounded(self):
        ctrl, store = make_controller()
        store.audit_limit = 5
        for i in range(10):
            await ctrl.audit(GOD, "ping", detail={"i": i})
        events = await store.list_audit(limit=50)
        self.assertEqual(len(events), 5)


if __name__ == "__main__":
    unittest.main()
