"""Demo walkthrough: define flags, set rules, evaluate for several users."""

from datetime import datetime, timedelta, timezone

from src.flags import (Client, MemoryStore, Rule, define_flags, flag_boolean,
                       flag_json, flag_variant)

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)


def main() -> None:
    registry = define_flags({
        "checkout.new-flow": flag_boolean(
            default=False, description="New one-page checkout"),
        "pricing.variant": flag_variant(
            default="control", variants=["control", "a", "b"],
            description="Pricing page variant"),
        "search.config": flag_json(
            default={"max_results": 20}, description="Search defaults"),
    })
    store = MemoryStore()
    store.set_rules("checkout.new-flow", [
        Rule(rule_id="beta-team", value=True, attributes={"plan": "beta"}),
        Rule(rule_id="rollout-50", value=True, rollout_percent=50),
    ], actor="ana")
    store.set_rules("pricing.variant", [
        Rule(rule_id="launch-week", value="a",
             window_start=NOW - timedelta(days=1),
             window_end=NOW + timedelta(days=6)),
    ], actor="ana")

    exposures = []
    client = Client(registry, store,
                    on_evaluation=lambda k, c, r: exposures.append((k, r.value)))
    users = [
        ("user-1", {"plan": "beta"}),
        ("user-2", {"plan": "free"}),
        ("user-3", {"plan": "free"}),
    ]
    print("Flag evaluations:")
    for key, attrs in users:
        ctx = {"targeting_key": key, "attributes": attrs}
        flow = client.evaluate("checkout.new-flow", ctx, now=NOW)
        variant = client.evaluate("pricing.variant", ctx, now=NOW)
        print(f"  {key} ({attrs['plan']}): new-flow={flow.value} "
              f"({flow.reason}, {flow.rule_id}), variant={variant.value}")

    print(f"\nUnknown flag -> default with a warning: "
          f"{client.value('no.such.flag', {'targeting_key': 'user-1'})!r}")
    print(f"Warnings: {client.warnings}")
    print(f"Audit log: {len(store.audit)} entr(ies) — "
          f"{store.audit[0]['actor']} set rules for checkout.new-flow")
    print(f"Exposures recorded via hook: {len(exposures)}")


if __name__ == "__main__":
    main()
