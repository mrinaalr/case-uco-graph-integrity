# CRIT-V-NONCONFORMING tells the originating agent only how many violations there are

SDK v1.33.0, `mcp_server/critic/deterministic.py` and `context_builder.py`. Found 2026-10-27.

## What happens

When SHACL validation fails, the critic emits one critical finding:

```
severity: critical
evidence: ["conforms=False", "verification_status=complete", "violations=5"]
rationale: "Graph validation is incomplete or non-conforming."
recommended_change: "Resolve SHACL/coverage failures before acceptance."
```

The review's `validation` block and the prompt package's `validation_summary` carry
`violation_count`, `stage_status` and a `safe_summary` ("Graph does not conform: 5 constraint
violation(s)."). Neither carries the validator's result messages (focus node, path, constraint),
so the agent that owns the edits cannot tell from the critic session what to change. `validate_graph`
on the same server does return them.

This is presumably deliberate (the prompt package is bounded and literal-free by design), but the
effect in a loop is that the critic's most severe finding is the least actionable one, and
finalization requires it to be resolved.

## What the harness does

The A1+QA arm attaches the `validate_graph` report to the NONCONFORMING finding before the findings
go back to the model, which is what an agent following the SDK README would do by calling the tool
itself. In the 30-case runs the per-pass `conforms` column shows whether the model then fixes it.

## Suggestion

Include the first N validator results (focus node IRI, result path, source shape, message) in the
finding's `evidence`, or a `validation_results` pointer in the review pass file, so the originating
agent has them in the session record rather than from a separate call it may not make.
