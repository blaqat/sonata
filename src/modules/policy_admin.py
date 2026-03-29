"""
Shared policy admin service layer for ``$policy`` (Discord) and ``policy`` (terminal).

Centralizes namespace validation, scope/target normalization, action and effect
validation, formatting of rule and group output, and persistence hooks. Command
entrypoints resolve Discord or terminal-specific references at the edge, then
delegate to this service.
"""

from modules.policy_api import (
    EFFECT_ALLOW,
    EFFECT_DENY,
    SCOPES,
    get_or_create_policy_api,
)


class PolicyAdminError(Exception):
    """Raised when a policy admin operation fails validation."""


class PolicyAdmin:
    """Shared service used by both Discord and terminal policy command surfaces."""

    def __init__(self, sonata):
        self.sonata = sonata
        self.api = get_or_create_policy_api(sonata)

    # ── Namespace helpers ────────────────────────────────────────────────

    def list_namespaces(self):
        return self.api.list_namespaces()

    def require_namespace(self, namespace):
        ns = namespace.strip().lower()
        if not self.api.has_namespace(ns):
            raise PolicyAdminError(f"Unknown namespace `{ns}`.")
        return ns

    # ── Validation ───────────────────────────────────────────────────────

    def validate_scope(self, scope):
        s = scope.strip().lower()
        if s not in SCOPES:
            raise PolicyAdminError(
                f"Invalid scope `{scope}`. Must be one of: {', '.join(SCOPES)}."
            )
        return s

    def validate_effect(self, effect):
        e = effect.strip().lower()
        if e not in {EFFECT_ALLOW, EFFECT_DENY}:
            raise PolicyAdminError(f"Effect must be `allow` or `deny`, got `{effect}`.")
        return e

    def validate_action(self, namespace, action):
        a = action.strip().lower()
        if not a:
            raise PolicyAdminError("Action cannot be empty.")
        expected_prefix = f"{namespace}."
        if not a.startswith(expected_prefix):
            raise PolicyAdminError(
                f"Action `{a}` must start with namespace prefix `{expected_prefix}`."
            )
        return a

    def normalize_target(self, target):
        t = str(target).strip()
        if not t:
            raise PolicyAdminError("Target cannot be empty.")
        return t

    # ── Read operations ──────────────────────────────────────────────────

    def show_rules(self, namespace, scope, target):
        ns = self.require_namespace(namespace)
        sc = self.validate_scope(scope)
        t = self.normalize_target(target)
        rules = self.api.get_scope_rules(ns, sc, t)
        if not rules:
            return f"No rules for `{ns}` {sc} `{t}`."
        lines = [f"Rules for `{ns}` {sc} `{t}`:"]
        for rule in sorted(rules, key=lambda r: r.action):
            lines.append(f"  {rule.action} → {rule.effect}")
        return "\n".join(lines)

    def list_groups(self, namespace):
        ns = self.require_namespace(namespace)
        groups = self.api.list_groups(ns)
        if not groups:
            return f"No groups in namespace `{ns}`."
        lines = [f"Groups in `{ns}`:"]
        for group_id in groups:
            lines.append(f"  {group_id}")
        return "\n".join(lines)

    def show_group(self, namespace, group_name):
        ns = self.require_namespace(namespace)
        group = self.api.get_group(ns, group_name)
        if group is None:
            raise PolicyAdminError(f"Group `{group_name}` not found in `{ns}`.")
        group_id = group["id"]
        members = group["members"]
        roles = group["roles"]
        rules = self.api.get_scope_rules(ns, "group", group_id)

        lines = [f"Group `{group_id}`:"]
        lines.append(f"  Members: {', '.join(members) if members else '(none)'}")
        lines.append(f"  Roles: {', '.join(roles) if roles else '(none)'}")
        if rules:
            lines.append("  Rules:")
            for rule in sorted(rules, key=lambda r: r.action):
                lines.append(f"    {rule.action} → {rule.effect}")
        else:
            lines.append("  Rules: (none)")
        return "\n".join(lines)

    # ── Write operations ─────────────────────────────────────────────────

    def set_rule(self, namespace, scope, target, action, effect):
        ns = self.require_namespace(namespace)
        sc = self.validate_scope(scope)
        t = self.normalize_target(target)
        a = self.validate_action(ns, action)
        e = self.validate_effect(effect)
        rule = self.api.set_rule(ns, sc, t, a, e)
        self._persist(ns)
        return f"Set `{a}` → `{e}` on {sc} `{t}` in `{ns}`."

    def remove_rule(self, namespace, scope, target, action):
        ns = self.require_namespace(namespace)
        sc = self.validate_scope(scope)
        t = self.normalize_target(target)
        a = self.validate_action(ns, action)
        removed = self.api.remove_rule(ns, sc, t, a)
        if not removed:
            raise PolicyAdminError(
                f"No rule `{a}` on {sc} `{t}` in `{ns}` to remove."
            )
        self._persist(ns)
        return f"Removed `{a}` from {sc} `{t}` in `{ns}`."

    def clear_scope(self, namespace, scope, target):
        ns = self.require_namespace(namespace)
        sc = self.validate_scope(scope)
        t = self.normalize_target(target)
        self.api.clear_scope(ns, sc, t)
        self._persist(ns)
        return f"Cleared all rules for {sc} `{t}` in `{ns}`."

    # ── Group write operations ───────────────────────────────────────────

    def upsert_group(self, namespace, group_name, *, members=None, role_ids=None):
        ns = self.require_namespace(namespace)
        name = group_name.strip().lower()
        if not name:
            raise PolicyAdminError("Group name cannot be empty.")
        member_list = _parse_csv(members) if isinstance(members, str) else members
        role_list = _parse_csv(role_ids) if isinstance(role_ids, str) else role_ids
        group_id = self.api.upsert_group(
            ns, name, members=member_list, role_ids=role_list
        )
        self._persist(ns)
        return f"Upserted group `{group_id}`."

    def remove_group(self, namespace, group_name):
        ns = self.require_namespace(namespace)
        removed = self.api.remove_group(ns, group_name)
        if not removed:
            raise PolicyAdminError(f"Group `{group_name}` not found in `{ns}`.")
        self._persist(ns)
        return f"Removed group `{group_name}` from `{ns}`."

    def add_group_member(self, namespace, group_name, user_id):
        ns = self.require_namespace(namespace)
        self.api.add_group_member(ns, group_name, user_id)
        self._persist(ns)
        return f"Added `{user_id}` to group `{group_name}` in `{ns}`."

    def remove_group_member(self, namespace, group_name, user_id):
        ns = self.require_namespace(namespace)
        removed = self.api.remove_group_member(ns, group_name, user_id)
        if not removed:
            raise PolicyAdminError(
                f"User `{user_id}` not in group `{group_name}` in `{ns}`."
            )
        self._persist(ns)
        return f"Removed `{user_id}` from group `{group_name}` in `{ns}`."

    def add_group_role(self, namespace, group_name, role_id):
        ns = self.require_namespace(namespace)
        self.api.bind_group_role(ns, group_name, role_id)
        self._persist(ns)
        return f"Bound role `{role_id}` to group `{group_name}` in `{ns}`."

    def remove_group_role(self, namespace, group_name, role_id):
        ns = self.require_namespace(namespace)
        removed = self.api.unbind_group_role(ns, group_name, role_id)
        if not removed:
            raise PolicyAdminError(
                f"Role `{role_id}` not bound to group `{group_name}` in `{ns}`."
            )
        self._persist(ns)
        return f"Unbound role `{role_id}` from group `{group_name}` in `{ns}`."

    def set_group_rule(self, namespace, group_name, action, effect):
        ns = self.require_namespace(namespace)
        a = self.validate_action(ns, action)
        e = self.validate_effect(effect)
        self.api.set_group_rule(ns, group_name, a, e)
        self._persist(ns)
        return f"Set `{a}` → `{e}` on group `{group_name}` in `{ns}`."

    # ── Persistence ──────────────────────────────────────────────────────

    def _persist(self, namespace):
        # Chat namespace uses ChannelPolicies persistence (legacy path)
        if namespace == "chat" and hasattr(self.sonata, "chat"):
            self.sonata.chat.policy_manager._persist()
            return
        # Generic namespace persistence
        self._persist_namespace(namespace)

    def _persist_namespace(self, namespace):
        data = self._serialize_namespace(namespace)
        all_ns = self.sonata.config.get("policy_namespaces", {})
        all_ns[namespace] = data
        self.sonata.config.set(policy_namespaces=all_ns)
        if self.sonata.has("beacon"):
            branch = self.sonata.beacon.branch("policies").branch("namespaces")
            branch.illuminate(namespace, data)

    def _serialize_namespace(self, namespace):
        ns_rules = self.api._rules.get(namespace, {})
        serialized = {"rules": {}, "groups": {}}

        for scope in SCOPES:
            scope_map = ns_rules.get(scope, {})
            if scope == "group":
                continue
            for scope_id, rules in scope_map.items():
                for rule in rules:
                    key = f"{scope}:{scope_id}"
                    entry = serialized["rules"].setdefault(key, [])
                    entry.append({"action": rule.action, "effect": rule.effect})

        for group_id in self.api.list_groups(namespace):
            name = group_id.split(":", 1)[1] if ":" in group_id else group_id
            group_data = self.api.get_group(namespace, name)
            group_rules = self.api.get_scope_rules(namespace, "group", group_id)
            serialized["groups"][group_id] = {
                "members": group_data.get("members", []) if group_data else [],
                "roles": group_data.get("roles", []) if group_data else [],
                "rules": [
                    {"action": r.action, "effect": r.effect} for r in group_rules
                ],
            }

        return serialized

    def load_namespace(self, namespace):
        """Load persisted generic namespace state into PolicyAPI."""
        data = None
        if self.sonata.has("beacon"):
            branch = self.sonata.beacon.branch("policies").branch("namespaces")
            data = branch.discover(namespace)

        config_ns = self.sonata.config.get("policy_namespaces", {})
        config_data = config_ns.get(namespace)
        if config_data is not None:
            data = config_data

        if data is None:
            return

        for key, rules in (data.get("rules") or {}).items():
            parts = key.split(":", 1)
            if len(parts) != 2:
                continue
            scope, scope_id = parts
            for rule in rules:
                action = rule.get("action", "")
                effect = rule.get("effect", "")
                if action and effect:
                    try:
                        self.api.set_rule(namespace, scope, scope_id, action, effect)
                    except (ValueError, KeyError):
                        pass

        for group_id, group_data in (data.get("groups") or {}).items():
            name = group_id.split(":", 1)[1] if ":" in group_id else group_id
            self.api.upsert_group(
                namespace,
                name,
                members=group_data.get("members", []),
                role_ids=group_data.get("roles", []),
            )
            for rule in group_data.get("rules", []):
                action = rule.get("action", "")
                effect = rule.get("effect", "")
                if action and effect:
                    try:
                        self.api.set_group_rule(namespace, name, action, effect)
                    except (ValueError, KeyError):
                        pass

    def load_all_namespaces(self):
        """Load all persisted generic namespace state on startup."""
        config_ns = self.sonata.config.get("policy_namespaces", {})
        loaded = set()

        for ns_name in config_ns:
            if self.api.has_namespace(ns_name):
                self.load_namespace(ns_name)
                loaded.add(ns_name)

        if self.sonata.has("beacon"):
            branch = self.sonata.beacon.branch("policies").branch("namespaces")
            # Beacon discover at folder level returns dict of subfolders
            try:
                all_data = branch.discover("") or {}
            except Exception:
                all_data = {}
            for ns_name in all_data:
                if ns_name not in loaded and self.api.has_namespace(ns_name):
                    self.load_namespace(ns_name)


def _parse_csv(value):
    if value is None or value == "-":
        return None
    return [v.strip() for v in str(value).split(",") if v.strip()]


def get_or_create_policy_admin(sonata):
    admin = getattr(sonata, "_policy_admin", None)
    if isinstance(admin, PolicyAdmin):
        return admin
    admin = PolicyAdmin(sonata)
    setattr(sonata, "_policy_admin", admin)
    return admin
