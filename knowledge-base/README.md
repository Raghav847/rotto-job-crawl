# Persistent project knowledge base

This folder is the entry point for a fresh coding session. It complements the
one-page submission README and the longer execution checklist in `plan.md`.

## Read in this order

1. `status.md`: current milestone, verified commands/data, active work and blockers.
2. `architecture.md`: modules, persistence boundaries and runtime interfaces.
3. `decisions.md`: source-access findings, extraction rules, lifecycle and dedupe tradeoffs.
4. `plan.md` and the relevant findings documents for detailed evidence.

## Fresh-session procedure

- Inspect `git status --short`; unfinished changes may belong to the user or an earlier session.
- Confirm Docker/Postgres availability with `docker compose ps`.
- Treat database counts and current `output/report.json` as more current than historical notes.
- Continue the active task in `status.md`; validate assumptions against code and saved evidence.
- Update this knowledge base before ending a milestone or approaching a context limit.

## Additional references

- `accuracy-findings.md`: initial 20-row review and confirmed parser repairs.
- `efficiency-findings.md`: Indeed resource policy and before/after measurements.
- `access-findings.md`: access experiments and live integration/dedupe evidence.
- `discovery-findings.md`: bounded pagination/query/location evidence and limitations.
- `recovery-findings.md`: durable queue/checkpoint policy and live interruption/resume evidence.
- `reproducibility-findings.md`: uncached clean-source/fresh-database and incremental/offline-test rehearsal.
- `dedupe-findings.md`: frozen real-pair corpus, scoped reference matching and live canonical verification.
- `acceleration-findings.md`: queue-aware scaling, artefact fixes, random sampling/repairs, holdout and cost units.
- `tests/fixtures/lifecycle.json`: supplied version-1 offline fixture; never fetch its URLs.
- `task.txt`: full local contract, including private proxy details; never commit/copy it here.

Knowledge-base dates use UTC. The submission deadline is Saturday, October 10,
2026 at 6:12 PM EDT (22:12 UTC). Store no credentials or anonymous session material.
