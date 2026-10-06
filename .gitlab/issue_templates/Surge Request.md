## What should change

<!-- One or two sentences. Link the code, the failing job or the alert if there is one. -->

## Acceptance criteria

- [ ] 
- [ ] `python -m pytest -q` passes

## Can it wait for clean power?

Joule Thief runs this when the grid has clean surplus, within the deadline of its priority:
`critical` runs now · `high` within 4 h · `normal` within 24 h · `low` within 72 h.
Kind of work: `agent_session` (code change by an agent) · `ci_pipeline` (heavy test runs) ·
`security_scan` (DAST, fuzzing, full scans) · `dependency_upgrade`.

<!-- Edit the labels on the next line if the defaults are wrong. Because the labels are set here,
     the Surge Intake agent needs a single call instead of a full triage. -->
/label ~"priority::normal" ~"energy::agent_session" ~"surge::queued"
