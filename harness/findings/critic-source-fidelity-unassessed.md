# The critic has a source_fidelity dimension but no rule that assesses it

SDK v1.33.0, `mcp_server/critic`. Found 2026-10-27 while building the A1+QA arm.

## What happens

The critic scorecard defines eight dimensions, one of them `source_fidelity`, and the finding
vocabulary has a `source_fidelity` category. No deterministic rule produces a finding in that
category or scores that dimension. On every graph this harness has submitted (30 cases, three
documents each, source files passed as `source_paths`) the deterministic review returns

```
"source_fidelity": {"score": null, "assessed": false, "evidence": [], "hard_cap": null, "cap_reason": null}
```

while `semantic_precision`, `serializer_quality` and `schema_concept_conformance` are scored. The
dimension is filled only when an LLM critic is run (policy `manual` or `client_sampling`) and
chooses to assess it. The `coverage.py` rules that take source files (`CRIT-C-SOURCE-HASH`) compare
a ContentDataFacet hash against the file bytes; they do not compare asserted facts against the text.

## Why it matters

The deterministic checks measure validity and modeling structure. Whether the graph says what the
documents say is left to the model, which is the component under review. In the harness's
`baseline-v1` run the bare A1 serializer already scores precision 0.61 and recall 0.28 (value
scorer) against gold, so most of the quality loss is in faithfulness, which the loop cannot see.

## What the harness measures that a rule could

Each gold triple sits in one sentence span, and models are asked to cite spans. The scorer's error
classes map onto checks a deterministic rule could make from the graph, the serializer and the
source text:

| error class (harness) | candidate rule | what it would check |
|---|---|---|
| wrong_value | CRIT-F-LITERAL-NOT-IN-SPAN | a literal (name, address, date) on a node does not occur, normalized, in any source document |
| cross_document_conflation | CRIT-F-CROSS-DOCUMENT-LINK | a Relationship joins two entities whose key literals never share a document |
| duplicate_entity | CRIT-F-DUPLICATE-KEY | two nodes of one class carry the same normalized key literal |
| invented (unaligned endpoint) | CRIT-F-UNANCHORED-ENTITY | a node has no literal that occurs in any source document |
| wrong_relation | CRIT-F-KIND-OUTSIDE-TASK-VOCAB | kindOfRelationship outside a caller-supplied allowed list (see the relationship-lint finding) |
| misplaced_property | CRIT-F-TYPED-VALUE-UNDER-NAME | a value shaped like a typed facet property (email address, account number, street address) stored under `uco-core:name` instead of the facet property that carries it |

`harness/rule_coverage.py` tests every unsupported triple of a scored run against these rules
using only the graph, the documents and the task's relation list. On `baseline-v1` (value scorer,
final graphs):

| arm | unsupported triples | caught by at least one rule |
|---|---|---|
| A1 script | 402 | 278 (69%) |
| B control | 747 | 607 (81%) |
| A2 tools | 731 | 470 (64%) |

For A1 the largest class, `misplaced_property` (233 of 402: the right value on the right entity
under the wrong property, most often an email address or account number as `uco-core:name`), is
caught 132 times by the typed-value rule alone. The remaining misplaced properties are event types
stored as names, which need the gold's property mapping to detect. Date and time literals were
not tested by the literal rule. Full tables are in `results/baseline-v1/rule_coverage.md`.

Each is computable from `CanonicalGraphView` plus the `source_paths` already accepted by
`start_critic_review`, in the shape the critic expects (stable finding id from rule and target IRIs,
rationale, recommended change, verification method).
