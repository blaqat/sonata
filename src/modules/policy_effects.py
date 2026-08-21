"""
Side effects for policy rule changes.

Chat owns ``chat.protected`` meaning; Beacon owns encrypt-path rules.
This module syncs Beacon encrypt actions from channel-scoped ``chat.protected``.
"""

from __future__ import annotations

import re

from modules.policy_api import EFFECT_ALLOW, get_or_create_policy_api

GLOBAL_POLICY_SCOPE_ID = "__global__"


def ensure_beacon_namespace(sonata, api=None):
    if not sonata.hasPlugin("beacon"):
        return None
    api = api or get_or_create_policy_api(sonata)
    if api.has_namespace("beacon"):
        api.activate_namespace("beacon")
    else:
        api.register_namespace("beacon", plugin=True)
    return api


def beacon_chat_history_action(sonata, channel_id) -> str | None:
    if not sonata.hasPlugin("beacon"):
        return None
    beacon_home = getattr(getattr(sonata, "beacon", None), "home", None)
    if not beacon_home:
        return None
    # Match Beacon path normalization so encrypt rules evaluate against the same key.
    normalized = re.sub(
        r"/+", "/", str(beacon_home).replace("\\", "/")
    ).strip("/").lower()
    return f"beacon.encrypt.path.{normalized}/chat/value/i{channel_id}"


def clear_beacon_chat_history_rule(sonata, channel_id, api=None) -> None:
    api = ensure_beacon_namespace(sonata, api)
    if api is None:
        return
    action = beacon_chat_history_action(sonata, channel_id)
    if action is None:
        return
    api.remove_rule("beacon", "guild", GLOBAL_POLICY_SCOPE_ID, action)


def sync_chat_protected_effects(sonata, api=None, *, channel_ids=None) -> None:
    """Align Beacon encrypt-path rules with channel ``chat.protected`` allow rules."""
    api = api or get_or_create_policy_api(sonata)
    if not api.has_namespace("chat"):
        return
    beacon_api = ensure_beacon_namespace(sonata, api)
    if beacon_api is None:
        return

    # Wipe prior chat-history encrypt rules first so cleared channel scopes
    # (unprotect / remove) do not leave stale Beacon allows behind.
    for rule in list(
        beacon_api.get_scope_rules("beacon", "guild", GLOBAL_POLICY_SCOPE_ID)
    ):
        action = rule.action
        if action.startswith("beacon.encrypt.path.") and "/chat/value/i" in action:
            beacon_api.remove_rule(
                "beacon", "guild", GLOBAL_POLICY_SCOPE_ID, action
            )

    if channel_ids is None:
        channel_ids = api.list_scope_ids("chat", "channel")
    else:
        channel_ids = [str(cid) for cid in channel_ids]

    for channel_id in channel_ids:
        action = beacon_chat_history_action(sonata, channel_id)
        if action is None:
            continue
        protected = False
        for rule in api.get_scope_rules("chat", "channel", channel_id):
            if rule.action == "chat.protected" and rule.effect == EFFECT_ALLOW:
                protected = True
                break
        if protected:
            beacon_api.set_rule(
                "beacon",
                "guild",
                GLOBAL_POLICY_SCOPE_ID,
                action,
                EFFECT_ALLOW,
            )

    island = sonata.beacon.branch("chat").branch("value")
    recast = getattr(island, "recast", None)
    if not callable(recast):
        return
    for channel_id in channel_ids:
        recast(f"i{channel_id}")
