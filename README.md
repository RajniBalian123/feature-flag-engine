# Feature Flag Engine — Demo

A feature flag SDK, rebuilt from scratch with synthetic data. Code declares
flags with types; the store controls their state and rules; the server
evaluates and the client gets an evaluated snapshot. It never throws — a
missing flag or a stale cache falls back to the code default.

This is a personal demo project. It captures the pattern — typed registry,
rule evaluation, percentage rollout, audit log — without any client code,
client data, or proprietary material.

## The problem

Shipping a feature to everyone at once is a bet. Shipping it behind a flag
is a dial: roll it out to 10% of users, to one team, inside a time window,
and roll it back in seconds if it breaks. The flag system has to be boring
and safe, because it runs on every request: it must never throw, never
leak rules to the client, and never lose the record of who changed what.

## How it works

```
Code declares flags (typed registry):
  'checkout.new-flow'  boolean, default False
  'pricing.variant'    variant control/a/b, default 'control'
  'search.config'      JSON, default {max_results: 20}

Store controls state and rules (per flag):
  - attribute rules  (e.g. plan == 'beta')
  - time windows     (UTC only, e.g. launch week)
  - percentage rollout (stable hash of targeting key + flag)
  - rule priority    (first matching rule wins)

Evaluation (server-side):
  context = {targeting_key, attributes}
  -> first matching rule decides, else the default
  -> result includes {value, reason, rule_id} so anyone can answer
     "why did this user get true?"
  -> missing key -> default + warn; stale cache -> default; never throw
```

- **Code declares, store controls.** Typed keys in code, runtime control
  without a redeploy. Boot sync is additive-only: missing declared flags
  are upserted, never deleted or overwritten.
- **Rules never leave the server.** The client gets an evaluated snapshot,
  not the rules.
- **Audit log.** Every mutation is recorded: who changed what, when.
- **Cache with TTL poll.** Evaluations read an in-memory cache refreshed
  every 15 seconds; a stale cache serves the default, not an error.

## Run it

```bash
python -m src.run_demo
```

Pure standard library, no dependencies. It defines three flags, evaluates
them for several users, and shows the audit log and the fallbacks.

Run the checks:

```bash
python -m unittest discover -s tests -v
```

## What this proves

- **Stable rollout.** The same user always lands in the same bucket —
  the hash is over targeting key + flag name, not random.
- **Priority works.** The first matching rule wins; a beta-user rule beats
  a 50% rollout rule for the same flag.
- **Time windows are UTC-only.** No timezone math in the evaluator.
- **Never throws.** A missing flag returns the default with a warning;
  a broken rule is skipped, not fatal.
- **Audit trail.** Every flag change is logged with who and when.

## Layout

- `src/flags.py` — registry, store, evaluation engine, client, audit log.
- `src/run_demo.py` — the demo walkthrough.
- `docs/design.md` — the full design: decisions, evaluation, stores,
  packaging.
- `tests/` — checks for rollout stability, priority, windows, fallbacks,
  and audit.

## What production adds

Drizzle/Postgres and Redis stores, a React provider with hooks, a Next.js
snapshot endpoint, and an admin API for flag CRUD. None of those are
claimed here — the demo is the evaluation engine and the safety rules,
local only.
