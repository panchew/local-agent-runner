# Mutation check: are the verification checks sensitive?

**Verdict: PASS**. Baseline: 29 checks, 0 failing. Each row disables one protection in `examples/ticket_service/ticket_tools.py` and re-runs the suite. *killed* means the expected checks went red.

| ID | Protection disabled | Expected to fail | Actually failed | Status |
|---|---|---|---|---|
| M01 | no redaction of secrets in tool output | SEC-01 | SEC-01 | killed |
| M02 | truncate service error before redacting (partial-key leak) | SEC-01 | SEC-01 | killed |
| M03 | follow redirects | SEC-04 | SEC-04 | killed |
| M04 | no ticket_id format validation | SEC-03 | SEC-03 | killed |
| M05 | allow plain http to any host | SEC-05 | SEC-05 | killed |
| M06 | no streaming size cap (only the declared Content-Length check remains) | SEC-09 | SEC-09 | killed |
| M07 | fresh idempotency key per tool call (repeat calls not deduplicated) | IDEM-01, IDEM-06 | IDEM-01, IDEM-06, IDEM-08, INT-02, INT-06 | killed |
| M07b | fresh idempotency key per transport retry | IDEM-02, IDEM-03 | IDEM-01, IDEM-02, IDEM-03, IDEM-06, IDEM-08, INT-02, INT-06 | killed |
| M08 | no idempotency key sent at all | IDEM-01, IDEM-02 | IDEM-01, IDEM-02, IDEM-03, IDEM-04, IDEM-05, IDEM-06, IDEM-07, IDEM-08, INT-01, INT-02, INT-04, INT-05, INT-06, SEC-01, SEC-08 | killed |
| M09 | no transport retries | IDEM-02, IDEM-03, IDEM-04 | IDEM-02, IDEM-03, IDEM-04, IDEM-05, IDEM-06, INT-06, SEC-08 | killed |
| M10 | idempotency key not scoped to the run | IDEM-08 | IDEM-08 | killed |
| M11 | no response signature verification | INT-02, INT-03 | INT-02, INT-03 | killed |
| M12 | no semantic check that the returned ticket matches the request | INT-04 | INT-04 | killed |
| M13 | secrets passed to the model-facing schema | SEC-01 | SEC-01, SEC-07 | killed |
