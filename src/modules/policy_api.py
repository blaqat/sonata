from __future__ import annotations

from dataclasses import dataclass, field


SCOPES = ("guild", "channel", "user")
EVAL_PRECEDENCE = ("user", "channel", "guild")
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
        }

        seen_allow = False
        for scope in EVAL_PRECEDENCE:
            scope_id_key = scope_ids[scope]
            if scope_id_key is None:
                continue

            decision = self._evaluate_scope(key, scope, scope_id_key, action_key)
            if decision == EFFECT_DENY:
                return False
            if decision == EFFECT_ALLOW:
                seen_allow = True

        if seen_allow:
            return True

        return self._resolve_default(ns, action_key, default)

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
