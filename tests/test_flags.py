"""Checks for rollout stability, priority, windows, fallbacks, audit."""

import unittest
from datetime import datetime, timedelta, timezone

from src.flags import (Client, MemoryStore, Rule, bucket, define_flags,
                       flag_boolean, flag_variant)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def make_client(rules=None):
    registry = define_flags({
        "checkout.new-flow": flag_boolean(default=False),
        "pricing.variant": flag_variant(default="control",
                                        variants=["control", "a", "b"]),
    })
    store = MemoryStore()
    if rules:
        for key, rs in rules.items():
            store.set_rules(key, rs, actor="tester")
    return Client(registry, store), store


class TestRollout(unittest.TestCase):
    def test_bucket_is_stable(self):
        self.assertEqual(bucket("user-1", "checkout.new-flow"),
                         bucket("user-1", "checkout.new-flow"))
        self.assertIn(bucket("user-1", "checkout.new-flow"), range(100))

    def test_rollout_is_deterministic_per_user(self):
        client, _ = make_client({"checkout.new-flow": [
            Rule(rule_id="r50", value=True, rollout_percent=50)]})
        ctx = {"targeting_key": "user-7", "attributes": {}}
        first = client.value("checkout.new-flow", ctx, now=NOW)
        second = client.value("checkout.new-flow", ctx, now=NOW)
        self.assertEqual(first, second)

    def test_rollout_splits_users(self):
        client, _ = make_client({"checkout.new-flow": [
            Rule(rule_id="r50", value=True, rollout_percent=50)]})
        results = {client.value("checkout.new-flow",
                                {"targeting_key": f"user-{i}", "attributes": {}},
                                now=NOW)
                   for i in range(20)}
        self.assertEqual(results, {True, False})  # some in, some out


class TestPriorityAndWindows(unittest.TestCase):
    def test_first_matching_rule_wins(self):
        client, _ = make_client({"checkout.new-flow": [
            Rule(rule_id="beta", value=True, attributes={"plan": "beta"}),
            Rule(rule_id="r50", value=True, rollout_percent=0)]})
        ev = client.evaluate("checkout.new-flow",
                             {"targeting_key": "u", "attributes": {"plan": "beta"}},
                             now=NOW)
        self.assertEqual(ev.rule_id, "beta")

    def test_time_window(self):
        client, _ = make_client({"pricing.variant": [
            Rule(rule_id="launch", value="a",
                 window_start=NOW - timedelta(days=1),
                 window_end=NOW + timedelta(days=1))]})
        ctx = {"targeting_key": "u", "attributes": {}}
        self.assertEqual(client.value("pricing.variant", ctx, now=NOW), "a")
        self.assertEqual(client.value(
            "pricing.variant", ctx, now=NOW + timedelta(days=5)), "control")


class TestSafety(unittest.TestCase):
    def test_unknown_flag_returns_default_and_warns(self):
        client, _ = make_client()
        ev = client.evaluate("no.such.flag", {"targeting_key": "u"}, now=NOW)
        self.assertIsNone(ev.value)
        self.assertTrue(any("unknown flag" in w for w in client.warnings))

    def test_audit_log_records_changes(self):
        _, store = make_client({"checkout.new-flow": [
            Rule(rule_id="r", value=True)]})
        self.assertEqual(len(store.audit), 1)
        self.assertEqual(store.audit[0]["actor"], "tester")
        self.assertEqual(store.audit[0]["flag"], "checkout.new-flow")


if __name__ == "__main__":
    unittest.main()
