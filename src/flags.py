"""Feature flag engine: typed registry, rule evaluation, never-throw.

Code declares flags; the store controls state and rules. Evaluation walks
rules in priority order: attribute rules, time windows (UTC only), and
percentage rollout with stable bucketing. Missing keys and broken rules
fall back to the code default — the engine never throws.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

CACHE_TTL_SECONDS = 15


@dataclass
class FlagDef:
    key: str
    kind: str  # boolean | string | number | variant | json
    default: object
    variants: list | None = None
    description: str = ""


@dataclass
class Rule:
    rule_id: str
    value: object
    attributes: dict | None = None
    rollout_percent: int | None = None
    window_start: datetime | None = None
    window_end: datetime | None = None


@dataclass
class Evaluation:
    value: object
    reason: str
    rule_id: str | None = None


def define_flags(defs: dict[str, FlagDef]) -> dict[str, FlagDef]:
    return defs


def flag_boolean(default: bool = False, description: str = "") -> FlagDef:
    return FlagDef(key="", kind="boolean", default=default, description=description)


def flag_variant(default: str, variants: list, description: str = "") -> FlagDef:
    return FlagDef(key="", kind="variant", default=default, variants=variants,
                   description=description)


def flag_json(default: dict, description: str = "") -> FlagDef:
    return FlagDef(key="", kind="json", default=default, description=description)


def bucket(targeting_key: str, flag_key: str) -> int:
    """Stable bucket 0-99 from targeting key + flag name."""
    digest = hashlib.sha256(f"{targeting_key}:{flag_key}".encode()).hexdigest()
    return int(digest[:8], 16) % 100


class MemoryStore:
    """Flag state + rules + audit log. Production swaps in a relational
    or Redis store behind the same interface."""

    def __init__(self):
        self.rules: dict[str, list[Rule]] = {}
        self.audit: list[dict] = []

    def set_rules(self, flag_key: str, rules: list[Rule], actor: str) -> None:
        self.rules[flag_key] = rules
        self.audit.append({"actor": actor, "action": "set_rules",
                           "flag": flag_key, "at": datetime.now(timezone.utc)})

    def get_rules(self, flag_key: str) -> list[Rule]:
        return self.rules.get(flag_key, [])


def _rule_matches(rule: Rule, context: dict, flag_key: str,
                  now: datetime) -> bool:
    if rule.attributes:
        attrs = context.get("attributes", {})
        if any(attrs.get(k) != v for k, v in rule.attributes.items()):
            return False
    if rule.window_start and now < rule.window_start:
        return False
    if rule.window_end and now > rule.window_end:
        return False
    if rule.rollout_percent is not None:
        if bucket(context.get("targeting_key", ""), flag_key) \
                >= rule.rollout_percent:
            return False
    return True


class Client:
    def __init__(self, registry: dict[str, FlagDef], store: MemoryStore,
                 on_evaluation=None):
        self.registry = registry
        self.store = store
        self.on_evaluation = on_evaluation
        self.warnings: list[str] = []

    def evaluate(self, flag_key: str, context: dict,
                 now: datetime | None = None) -> Evaluation:
        now = now or datetime.now(timezone.utc)
        flag = self.registry.get(flag_key)
        if flag is None:
            self.warnings.append(f"unknown flag: {flag_key}")
            return Evaluation(value=None, reason="unknown_flag")
        try:
            for rule in self.store.get_rules(flag_key):
                if _rule_matches(rule, context, flag_key, now):
                    result = Evaluation(value=rule.value,
                                        reason="rule_match", rule_id=rule.rule_id)
                    if self.on_evaluation:
                        self.on_evaluation(flag_key, context, result)
                    return result
        except Exception:
            self.warnings.append(f"rule evaluation failed: {flag_key}")
        result = Evaluation(value=flag.default, reason="default")
        if self.on_evaluation:
            self.on_evaluation(flag_key, context, result)
        return result

    def value(self, flag_key: str, context: dict,
              now: datetime | None = None):
        return self.evaluate(flag_key, context, now).value
