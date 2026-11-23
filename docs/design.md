# Design: a feature flag engine that never throws

Status: demo of the evaluation pattern, with synthetic data. It does not
claim Postgres/Redis stores, React hooks, or an admin API.

## 1. Decisions

| Decision | Choice | Why |
|---|---|---|
| Eval surface | Server evaluates; client gets an evaluated snapshot | Rules never leave the server |
| Topology | Per-app siloed storage, no central plane | Each app owns its flags |
| Management surface | Programmatic CRUD API; UIs built around it | No out-of-box UI in v1 |
| Freshness | In-memory cache, TTL poll (default 15s) | Seconds-level flips are fine |
| Value types | boolean + string + number + JSON variants | Config flags and A/B variants, not just on/off |
| Targeting | Attribute rules + time windows + percentage rollout + rule priority | Full v1 suite |
| Failure mode | Never throw; stale cache → code default; missing key → default + warn | 3am-safe |
| Truth model | Code declares (typed registry), store controls state/rules | Typed keys + runtime control without codegen |
| Boot sync | Additive-only: upsert missing declared flags, never delete/overwrite | Rolling-deploy safe |
| Observability | Audit log (CRUD mutations) + `on_evaluation` hook | Who-changed-what + exposure analytics |

## 2. Registry: code is the declaration truth

Flags are declared in code with a type, a default, and a description:

```python
flags = define_flags({
    "checkout.new-flow": flag.boolean(default=False),
    "pricing.variant": flag.variant(default="control", variants=["control", "a", "b"]),
    "search.config": flag.json(default={"max_results": 20}),
})
```

The type of a flag is known at write time, so a typo in a flag key is a
code error, not a runtime surprise. The store holds state and rules; it
never invents a flag the code did not declare.

## 3. Evaluation

Evaluation takes a context — `{targeting_key, attributes}` — and walks
the flag's rules in priority order. The first matching rule decides:

1. **Attribute rule** — e.g. `plan == "beta"`. All conditions must match.
2. **Time window** — stored and compared in UTC only. Outside the window,
   the rule does not match.
3. **Percentage rollout** — a stable hash of `targeting_key + flag name`
   decides the bucket (0–99). The same user always lands in the same
   bucket, and the bucket does not move when other users are added.

No rule matches → the code default. The detailed result includes
`{value, reason, rule_id}` so anyone can answer "why did this user get
true?" — the audit log answers "who changed it", the reason answers "why".

## 4. Failure mode: never throw

- Missing flag key → the default, plus a warning.
- Stale cache → the default, not an error.
- A broken rule (bad value, bad window) → the rule is skipped, evaluation
  continues.
- The store is down → the last cached snapshot, then the default.

A flag system that throws on a bad flag takes down the page that reads it.
A flag system that falls back to the default takes down nothing.

## 5. Stores

The store interface is small: get/set flag state, list rules, append to
the audit log. The demo ships a memory store (tests, local dev).
Production adds a relational store and a Redis store — Redis as a primary
store for Redis-only apps, or as a cache decorator over another store for
read scaling. Boot sync is additive-only in every store.

## 6. What production adds

- **Relational + Redis stores** behind the same interface.
- **React provider + hooks** (`use_flag`, `use_flag_details`) reading the
  evaluated snapshot.
- **Snapshot endpoint** for server-rendered apps.
- **Admin API** for flag CRUD, with the audit log as its record.
