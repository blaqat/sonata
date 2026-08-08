"""
Shared command dispatch for Discord ``$policy`` and terminal ``policy``.

Entrypoints resolve Discord/terminal-specific mentions and validate guild
membership at the edge, then call ``dispatch_policy_command`` with those
resolvers injected. Mutation/persistence stays in ``PolicyAdmin``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


ResolveTarget = Callable[[str, str], Awaitable[str]]


async def dispatch_policy_command(
    admin,
    action: str,
    args,
    usage: str,
    *,
    resolve_target: ResolveTarget,
    format_namespace: Callable[[str], str] | None = None,
    resolve_user_id: Callable[[str], str] | None = None,
    resolve_role_id: Callable[[str], str] | None = None,
    resolve_members_csv: Callable[[Any], Any] | None = None,
    resolve_roles_csv: Callable[[Any], Any] | None = None,
    validate_user: Callable[[str], Awaitable[str]] | None = None,
    validate_role: Callable[[str], Awaitable[str]] | None = None,
):
    """Route a policy CLI action to ``PolicyAdmin``.

    Returns a result string, ``usage`` when args are incomplete, or ``None``
    when ``action`` is unknown.
    """
    action = (action or "").lower().strip()
    args = list(args or [])

    if action == "namespaces":
        ns_list = admin.list_namespaces()
        if format_namespace is not None:
            ns_list = [format_namespace(n) for n in ns_list]
        return "Namespaces: " + ", ".join(ns_list)

    if action == "show":
        if len(args) < 3:
            return usage
        namespace, scope, raw_target = args[0], args[1], args[2]
        target = await resolve_target(scope, raw_target)
        return admin.show_rules(namespace, scope, target)

    if action == "set":
        if len(args) < 5:
            return usage
        namespace, scope, raw_target, act, effect = (
            args[0],
            args[1],
            args[2],
            args[3],
            args[4],
        )
        target = await resolve_target(scope, raw_target)
        return admin.set_rule(namespace, scope, target, act, effect)

    if action == "remove":
        if len(args) < 4:
            return usage
        namespace, scope, raw_target, act = args[0], args[1], args[2], args[3]
        target = await resolve_target(scope, raw_target)
        return admin.remove_rule(namespace, scope, target, act)

    if action == "clear":
        if len(args) < 3:
            return usage
        namespace, scope, raw_target = args[0], args[1], args[2]
        target = await resolve_target(scope, raw_target)
        return admin.clear_scope(namespace, scope, target)

    if action == "groups":
        return await _dispatch_groups(
            admin,
            args,
            usage,
            resolve_user_id=resolve_user_id,
            resolve_role_id=resolve_role_id,
            resolve_members_csv=resolve_members_csv,
            resolve_roles_csv=resolve_roles_csv,
            validate_user=validate_user,
            validate_role=validate_role,
        )

    return None


async def _dispatch_groups(
    admin,
    args,
    usage,
    *,
    resolve_user_id,
    resolve_role_id,
    resolve_members_csv,
    resolve_roles_csv,
    validate_user,
    validate_role,
):
    if len(args) < 2:
        return usage
    sub = args[0].lower()

    if sub == "list":
        return admin.list_groups(args[1])

    if sub == "show":
        if len(args) < 3:
            return usage
        return admin.show_group(args[1], args[2])

    if sub == "upsert":
        if len(args) < 3:
            return usage
        namespace, group = args[1], args[2]
        members = args[3] if len(args) > 3 else None
        roles = args[4] if len(args) > 4 else None
        if resolve_members_csv is not None:
            members = resolve_members_csv(members)
        if resolve_roles_csv is not None:
            roles = resolve_roles_csv(roles)
        return admin.upsert_group(namespace, group, members=members, role_ids=roles)

    if sub == "remove":
        if len(args) < 3:
            return usage
        return admin.remove_group(args[1], args[2])

    if sub == "member":
        if len(args) < 5:
            return usage
        op, namespace, group, user = args[1], args[2], args[3], args[4]
        user_id = resolve_user_id(user) if resolve_user_id is not None else user
        if validate_user is not None:
            user_id = await validate_user(user_id)
        if op == "add":
            return admin.add_group_member(namespace, group, user_id)
        if op == "remove":
            return admin.remove_group_member(namespace, group, user_id)
        return usage

    if sub == "role":
        if len(args) < 5:
            return usage
        op, namespace, group, role = args[1], args[2], args[3], args[4]
        role_id = resolve_role_id(role) if resolve_role_id is not None else role
        if validate_role is not None:
            role_id = await validate_role(role_id)
        if op == "add":
            return admin.add_group_role(namespace, group, role_id)
        if op == "remove":
            return admin.remove_group_role(namespace, group, role_id)
        return usage

    return usage
