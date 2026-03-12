from __future__ import annotations

from dataclasses import dataclass, field


SCOPES = ("guild", "channel", "group", "user")
EVAL_PRECEDENCE = ("user", "group", "channel", "guild")
EFFECT_ALLOW = "allow"
EFFECT_DENY = "deny"


@dataclass
class PolicyRule:
    scope: str
    scope_id: str
    action: str
    effect: str


@dataclass
class PolicyNamespace:
    name: str
    plugin: bool = False
    active: bool = True
    default_decisions: dict[str, bool] = field(default_factory=dict)


class PolicyAPI:
    def __init__(self):
        self._namespaces: dict[str, PolicyNamespace] = {}
        self._rules: dict[str, dict[str, dict[str, list[PolicyRule]]]] = {}
        self._groups: dict[str, dict[str, set[str]]] = {}
        self._group_roles: dict[str, dict[str, set[str]]] = {}
        self._role_resolver = None
        self.register_namespace("core", plugin=False)

    def register_namespace(
        self,
        namespace: str,
        *,
        plugin: bool = False,
        default_decisions: dict[str, bool] | None = None,
    ) -> PolicyNamespace:
        key = self._normalize_namespace(namespace)
        if key in self._namespaces:
            raise ValueError(f"Namespace '{key}' is already registered")

        ns = PolicyNamespace(
            name=key,
            plugin=plugin,
            active=True,
            default_decisions=self._normalize_default_decisions(default_decisions),
        )
        self._namespaces[key] = ns
        self._rules[key] = {scope: {} for scope in SCOPES}
        self._groups[key] = {}
        self._group_roles[key] = {}
        return ns

    def has_namespace(self, namespace: str) -> bool:
        return self._normalize_namespace(namespace) in self._namespaces

    def list_namespaces(self) -> list[str]:
        return sorted(self._namespaces.keys())

    def unload_namespace(self, namespace: str):
        key = self._normalize_namespace(namespace)
        if key == "core":
            raise ValueError("Core namespace cannot be unloaded")
        ns = self._require_namespace(key)
        ns.active = False

    def activate_namespace(self, namespace: str):
        key = self._normalize_namespace(namespace)
        ns = self._require_namespace(key)
        ns.active = True

    def set_role_resolver(self, resolver):
        self._role_resolver = resolver

    def normalize_group_id(self, namespace: str, group_name: str) -> str:
        ns = self._normalize_namespace(namespace)
        name = str(group_name or "").strip().lower()
        if not name:
            raise ValueError("Group name is required")
        return f"{ns}:{name}"

    def upsert_group(
        self,
        namespace: str,
        group_name: str,
        *,
        members=None,
        role_ids=None,
    ) -> str:
        key = self._normalize_namespace(namespace)
        self._require_namespace(key)
        group_id = self.normalize_group_id(key, group_name)

        entry = self._groups[key].setdefault(group_id, set())
        if members is not None:
            entry.clear()
            entry.update(self._normalize_identifier_set(members))

        roles = self._group_roles[key].setdefault(group_id, set())
        if role_ids is not None:
            roles.clear()
            roles.update(self._normalize_identifier_set(role_ids))

        return group_id

    def remove_group(self, namespace: str, group_name: str) -> bool:
        key = self._normalize_namespace(namespace)
        self._require_namespace(key)
        group_id = self.normalize_group_id(key, group_name)
        removed = False

        if group_id in self._groups[key]:
            self._groups[key].pop(group_id, None)
            removed = True
        if group_id in self._group_roles[key]:
            self._group_roles[key].pop(group_id, None)
            removed = True

        self._rules[key]["group"].pop(group_id, None)
        return removed

    def add_group_member(self, namespace: str, group_name: str, user_id) -> str:
        key = self._normalize_namespace(namespace)
        group_id = self.upsert_group(key, group_name)
        self._groups[key][group_id].add(self._normalize_scope_id(user_id))
        return group_id

    def remove_group_member(self, namespace: str, group_name: str, user_id) -> bool:
        key = self._normalize_namespace(namespace)
        group_id = self.normalize_group_id(key, group_name)
        members = self._groups.get(key, {}).get(group_id)
        if not members:
            return False
        user_key = self._normalize_scope_id(user_id)
        if user_key not in members:
            return False
        members.remove(user_key)
        return True

    def bind_group_role(self, namespace: str, group_name: str, role_id) -> str:
        key = self._normalize_namespace(namespace)
        group_id = self.upsert_group(key, group_name)
        self._group_roles[key][group_id].add(self._normalize_scope_id(role_id))
        return group_id

    def unbind_group_role(self, namespace: str, group_name: str, role_id) -> bool:
        key = self._normalize_namespace(namespace)
        group_id = self.normalize_group_id(key, group_name)
        roles = self._group_roles.get(key, {}).get(group_id)
        if not roles:
            return False
        role_key = self._normalize_scope_id(role_id)
        if role_key not in roles:
            return False
        roles.remove(role_key)
        return True

    def list_groups(self, namespace: str) -> list[str]:
        key = self._normalize_namespace(namespace)
        self._require_namespace(key)
        return sorted(self._groups[key].keys())

    def get_group(self, namespace: str, group_name: str) -> dict[str, list[str]] | None:
        key = self._normalize_namespace(namespace)
        self._require_namespace(key)
        group_id = self.normalize_group_id(key, group_name)
        members = self._groups[key].get(group_id)
        roles = self._group_roles[key].get(group_id)
        if members is None and roles is None:
            return None
        return {
            "id": group_id,
            "members": sorted(members or []),
            "roles": sorted(roles or []),
        }

    def set_group_rule(
        self,
        namespace: str,
        group_name: str,
        action: str,
        effect: str,
    ) -> PolicyRule:
        key = self._normalize_namespace(namespace)
        group_id = self.normalize_group_id(key, group_name)
        self.upsert_group(key, group_name)
        return self.set_rule(key, "group", group_id, action, effect)

    def resolve_groups(
        self,
        namespace: str,
        *,
        user_id=None,
        role_ids=None,
    ) -> list[str]:
        key = self._normalize_namespace(namespace)
        self._require_namespace(key)

        normalized_user = self._optional_scope_id(user_id)
        resolved = set()

        if normalized_user is not None:
            for group_id, members in self._groups[key].items():
                if normalized_user in members:
                    resolved.add(group_id)

        roles = self._resolve_runtime_roles(key, normalized_user, role_ids)
        if roles:
            for group_id, mapped_roles in self._group_roles[key].items():
                if mapped_roles.intersection(roles):
                    resolved.add(group_id)

        return sorted(resolved)

    def set_rule(
        self,
        namespace: str,
        scope: str,
        scope_id,
        action: str,
        effect: str,
    ) -> PolicyRule:
        key = self._normalize_namespace(namespace)
        scope_key = self._normalize_scope(scope)
        scope_id_key = self._normalize_scope_id(scope_id)
        action_key = self._normalize_action(action)
        effect_key = self._normalize_effect(effect)

        self._require_namespace(key)
        rules = self._rules[key][scope_key].setdefault(scope_id_key, [])
        rules = [rule for rule in rules if rule.action != action_key]
        new_rule = PolicyRule(
            scope=scope_key,
            scope_id=scope_id_key,
            action=action_key,
            effect=effect_key,
        )
        rules.append(new_rule)
        self._rules[key][scope_key][scope_id_key] = rules
        return new_rule

    def remove_rule(self, namespace: str, scope: str, scope_id, action: str) -> bool:
        key = self._normalize_namespace(namespace)
        scope_key = self._normalize_scope(scope)
        scope_id_key = self._normalize_scope_id(scope_id)
        action_key = self._normalize_action(action)

        self._require_namespace(key)
        scope_map = self._rules[key][scope_key]
        rules = scope_map.get(scope_id_key, [])
        kept = [rule for rule in rules if rule.action != action_key]
        if len(kept) == len(rules):
            return False
        if kept:
            scope_map[scope_id_key] = kept
        else:
            scope_map.pop(scope_id_key, None)
        return True

    def clear_scope(self, namespace: str, scope: str, scope_id):
        key = self._normalize_namespace(namespace)
        scope_key = self._normalize_scope(scope)
        scope_id_key = self._normalize_scope_id(scope_id)
        self._require_namespace(key)
        self._rules[key][scope_key].pop(scope_id_key, None)

    def get_scope_rules(self, namespace: str, scope: str, scope_id) -> list[PolicyRule]:
        key = self._normalize_namespace(namespace)
        scope_key = self._normalize_scope(scope)
        scope_id_key = self._normalize_scope_id(scope_id)
        self._require_namespace(key)
        return list(self._rules[key][scope_key].get(scope_id_key, []))

    def evaluate(
        self,
        namespace: str,
        action: str,
        *,
        guild_id=None,
        channel_id=None,
        user_id=None,
        group_ids=None,
        role_ids=None,
        default: bool | None = None,
    ) -> bool:
        key = self._normalize_namespace(namespace)
        action_key = self._normalize_action(action)
        ns = self._namespaces.get(key)

        if ns is None or not ns.active:
            return self._resolve_default(ns, action_key, default)

        scope_ids = {
            "guild": self._optional_scope_id(guild_id),
            "channel": self._optional_scope_id(channel_id),
            "user": self._optional_scope_id(user_id),
            "group": self._resolve_group_scope_ids(
                key,
                group_ids=group_ids,
                user_id=user_id,
                role_ids=role_ids,
            ),
        }

        seen_allow = False
        for scope in EVAL_PRECEDENCE:
            ids = scope_ids[scope]
            if ids is None:
                continue

            if isinstance(ids, str):
                ids = [ids]

            decision = self._evaluate_scope_ids(key, scope, ids, action_key)
            if decision == EFFECT_DENY:
                return False
            if decision == EFFECT_ALLOW:
                seen_allow = True

        if seen_allow:
            return True

        return self._resolve_default(ns, action_key, default)

    def _evaluate_scope_ids(
        self,
        namespace: str,
        scope: str,
        scope_ids: list[str],
        action: str,
    ) -> str | None:
        saw_allow = False
        for scope_id_key in scope_ids:
            if scope_id_key is None:
                continue

            decision = self._evaluate_scope(namespace, scope, scope_id_key, action)
            if decision == EFFECT_DENY:
                return EFFECT_DENY
            if decision == EFFECT_ALLOW:
                saw_allow = True
        if saw_allow:
            return EFFECT_ALLOW
        return None

    def _evaluate_scope(
        self,
        namespace: str,
        scope: str,
        scope_id: str,
        action: str,
    ) -> str | None:
        rules = self._rules[namespace][scope].get(scope_id, [])
        if not rules:
            return None

        matched: list[tuple[int, PolicyRule]] = []
        for rule in rules:
            if self._matches(rule.action, action):
                matched.append((self._specificity(rule.action), rule))

        if not matched:
            return None

        highest = max(score for score, _ in matched)
        candidates = [rule for score, rule in matched if score == highest]
        if any(rule.effect == EFFECT_DENY for rule in candidates):
            return EFFECT_DENY
        if any(rule.effect == EFFECT_ALLOW for rule in candidates):
            return EFFECT_ALLOW
        return None

    def _resolve_default(
        self,
        namespace: PolicyNamespace | None,
        action: str,
        override_default: bool | None,
    ) -> bool:
        if override_default is not None:
            return bool(override_default)

        if namespace is None:
            return False

        matched: list[tuple[int, bool]] = []
        for pattern, decision in namespace.default_decisions.items():
            if self._matches(pattern, action):
                matched.append((self._specificity(pattern), bool(decision)))

        if not matched:
            return False

        highest = max(score for score, _ in matched)
        candidates = [decision for score, decision in matched if score == highest]
        if any(not decision for decision in candidates):
            return False
        return True

    def _require_namespace(self, namespace: str) -> PolicyNamespace:
        ns = self._namespaces.get(namespace)
        if ns is None:
            raise KeyError(f"Namespace '{namespace}' is not registered")
        return ns

    def _normalize_namespace(self, namespace: str) -> str:
        key = str(namespace or "").strip().lower()
        if not key:
            raise ValueError("Namespace is required")
        return key

    def _normalize_scope(self, scope: str) -> str:
        scope_key = str(scope or "").strip().lower()
        if scope_key not in SCOPES:
            raise ValueError(f"Invalid scope '{scope}'")
        return scope_key

    def _normalize_scope_id(self, scope_id) -> str:
        key = str(scope_id).strip()
        if not key:
            raise ValueError("Scope id is required")
        return key

    def _optional_scope_id(self, scope_id) -> str | None:
        if scope_id is None:
            return None
        key = str(scope_id).strip()
        return key or None

    def _normalize_identifier_set(self, values) -> set[str]:
        if values is None:
            return set()
        if not isinstance(values, (list, tuple, set)):
            values = [values]
        normalized = set()
        for value in values:
            key = self._optional_scope_id(value)
            if key is not None:
                normalized.add(key)
        return normalized

    def _resolve_runtime_roles(
        self, namespace: str, user_id: str | None, role_ids
    ) -> set[str]:
        role_set = self._normalize_identifier_set(role_ids)
        if role_set:
            return role_set

        if self._role_resolver is None:
            return set()
        if user_id is None:
            return set()

        try:
            resolved = self._role_resolver(namespace, user_id)
        except Exception:
            return set()
        return self._normalize_identifier_set(resolved)

    def _resolve_group_scope_ids(
        self,
        namespace: str,
        *,
        group_ids,
        user_id,
        role_ids,
    ) -> list[str]:
        if group_ids is not None:
            if not isinstance(group_ids, (list, tuple, set)):
                group_ids = [group_ids]
            normalized = set()
            for group_id in group_ids:
                if group_id is None:
                    continue
                group_key = str(group_id).strip().lower()
                if not group_key:
                    continue
                if not group_key.startswith(f"{namespace}:"):
                    group_key = self.normalize_group_id(namespace, group_key)
                normalized.add(group_key)
            return sorted(normalized)

        return self.resolve_groups(namespace, user_id=user_id, role_ids=role_ids)

    def _normalize_action(self, action: str) -> str:
        key = str(action or "").strip().lower()
        if not key:
            raise ValueError("Action is required")
        return key

    def _normalize_effect(self, effect: str) -> str:
        key = str(effect or "").strip().lower()
        if key not in {EFFECT_ALLOW, EFFECT_DENY}:
            raise ValueError("Effect must be 'allow' or 'deny'")
        return key

    def _normalize_default_decisions(
        self,
        decisions: dict[str, bool] | None,
    ) -> dict[str, bool]:
        if not decisions:
            return {}
        normalized = {}
        for action, decision in decisions.items():
            normalized[self._normalize_action(action)] = bool(decision)
        return normalized

    def _matches(self, pattern: str, action: str) -> bool:
        if pattern == action:
            return True
        if pattern.endswith("*"):
            return action.startswith(pattern[:-1])
        return False

    def _specificity(self, pattern: str) -> int:
        return len(pattern[:-1]) if pattern.endswith("*") else len(pattern)


def get_or_create_policy_api(sonata) -> PolicyAPI:
    api = getattr(sonata, "policy_api", None)
    if isinstance(api, PolicyAPI):
        return api
    api = PolicyAPI()
    setattr(sonata, "policy_api", api)
    return api
