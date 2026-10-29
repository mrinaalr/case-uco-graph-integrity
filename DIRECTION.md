# Direction: why this repo studies graph construction the way it does

Written 2026-10-27. This is the motivation and the path that led to the experiment in
[EXPERIMENT.md](EXPERIMENT.md); that file documents the methods, outputs and how to read them.

## The ambition

Modeling digital evidence as a CASE/UCO graph is slow by hand and unreliable by machine. The aim
of this work is to make it easier and trustworthy enough to use: data in, graphs out, true to
the source. Everything here is in service of one question: **which way of constructing a graph
from documents produces graphs that accurately reflect those documents, and what moves that?**

## Where we started

The first harness measured how faithfully a model turns generated case documents into a
CASE/UCO graph, against gold graphs we author and therefore know completely. Three arms: the
model writes a serializer script against the SDK (A1), the model writes the graph through
tool calls (A2), the model emits raw JSON-LD (B). The scorer aligns the produced graph to gold
and classes every unsupported statement.

The baseline showed the shape of the problem. Graphs were usually valid and much less often
true: the best arm got about six in ten statements right. The dominant error was not reading
but modeling, the right value on the right entity under the wrong property.

## The pivot: study the SDK's own workflow

The SDK under test has a documented way of working, and it is not tool calls. An agent writes a
custom serializer for the evidence source, that script produces the graph, and a critic loop
reviews the graph and the script: deterministic SHACL, graph-integrity, modeling-heuristic,
relationship-vocabulary and serializer-code checks first, an optional model critique second,
and the agent revises until it passes. That loop is the SDK's quality control.

So the object of study became the generated serializer, and the critic loop became the
treatment. A2's write tools were ours, not the SDK's, and were demoted to a reference point.

Three facts about the SDK made the treatment worth measuring rather than assuming:

- The critic's scorecard has a `source_fidelity` dimension and category, but no deterministic
  rule produces either. On every baseline graph it came back `assessed: false`. Faithfulness to
  the source is the one thing the loop cannot see.
- On the baseline graphs the critic fired two rules on essentially every node and every
  relationship (`CRIT-H-ORPHAN-TOP-LEVEL`, because there is no Investigation root, and
  `CRIT-V-RELATIONSHIP-LINT`, because none of the task's ten relation kinds is in the UCO
  vocabularies), plus one serializer rule. The first two ask for structure the task does not
  contain.
- The baseline's own repair rounds raised recall in 11 of 30 cases and lowered precision in 3,
  and introduced 71 unsupported statements under the strict scorer. Validation-driven fixes can
  add errors.

## What the critic-loop study found

A new arm ran the SDK's real critic session on the A1 serializer, fed the findings back to the
model to rewrite the script, and scored every pass. Two policies: deterministic checks only, and
the same model also acting as critic from the server's prompt package. 30 cases each, one 9B
model, deltas measured pass-to-pass within a case (the endpoint is not deterministic at
temperature 0 across runs).

| policy | revisions ran | crashed | gold fixed | gold regressed | precision | recall |
|---|---|---|---|---|---|---|
| deterministic | 22 | 8 | 2 | 5 | 0.554 to 0.495 | flat |
| model as critic | 34 | 8 | 4 | 47 | 0.534 to 0.449 | 0.468 to 0.451 |

Every one of the 47 regressions came from revisions answering the model's own
`source_fidelity` findings. The critic that could see the source made the graph less faithful
to it. Validity did not move either way.

Then the other direction: six simple deterministic rules computable from the graph and the
documents (literal not in source, typed value stored under a generic name, cross-document
link, duplicate key, unanchored entity, relation kind outside the task vocabulary) would have
flagged 69% of the baseline's unsupported statements and 82% of the critic runs'. None of the
rules the critic actually ran targets any of those statements.

The reading: on this model, the shipped QA loop moves neither validity nor fidelity in the right
direction, because it checks structure and vocabulary, not the source, and feeding those
findings back costs precision. Most of what the model gets wrong is modeling, and most of that is
deterministically checkable. Three findings for the SDK came out of this and sit in
`harness/findings/`.

## Where that points

If the errors are mostly modeling, and mostly checkable, then the fix at the source is not a
better critic on a model-written graph. It is to take the modeling away from the model: let it
read and cite, gate what it read against the text, and let a compiler do the ontology. That is
method C in [EXPERIMENT.md](EXPERIMENT.md), compared against the SDK's workflow (A) and direct
generation with and without training and defenses (B1 to B4), on a 100-case PDF benchmark.

## Working title

*Evidence-Grounded Graph Construction: Evaluating the Semantic Fidelity of Machine-Constructed
CASE/UCO Graphs.* Two questions: which existing approach produces the most reliable graphs,
and whether a different construction architecture improves reliability beyond training or
defending a model.
