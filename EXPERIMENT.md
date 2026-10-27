# Constructing graphs that hold to the evidence: the A/B/C experiment

Written 2026-10-27. Supersedes the arm layout in DIRECTION.md; the critic-loop findings there stand.

## The problem

Modeling evidence as a CASE/UCO graph is slow by hand and unreliable by machine. When a language
model does it, the graph is valid more often than it is true: in the baseline runs the best method
got six in ten of its statements right. The goal is to make graph construction from documents
easier and trustworthy enough to use, and to measure what moves it.

## The benchmark

100 generated cases, each a fraud or business-communication scenario with a gold graph authored
first and then rendered into 2 to 4 documents (memo, email, chat export, incident report). Every
gold triple is stated in exactly one sentence. Each document is a PDF with no annotations; the
methods receive the PDFs and nothing else about the case. Gold graphs validate under
`case_validate`. The scorer aligns the produced graph to gold entity by entity and classes every
unsupported statement (wrong value, wrong relation, wrong entity, conflation across documents,
misplaced property, duplicate entity, invented). Scores are comparable only under the same
freeze entry (`harness/FROZEN.md`, Freeze 4).

## The three methods

All three get the same task statement (`llm.SHARED`: model only what the documents state, the
core classes to use, the ten relation kinds) and the same model. They differ in who writes the
ontology.

**A. The SDK as shipped.** A coding agent with the SDK's MCP server follows the SDK's own
workflow: read the evidence, route it and look up classes and recipes, write a serializer with
`CASEGraph`, validate, run the critic loop, finalize. The harness contributes a file reader, a
"save and run this script" tool, and nothing in the graph. (`pipeline_sdk_agent.py`, arm
`a_sdk_agent`; the graph at the agent's first validation is also scored as `@first_validate`.)

**B. Direct generation.** The model reads the documents and emits the CASE/UCO JSON-LD in one
reply. No tools, no repair. (`pipeline_monolith.py`, arm `b_control`.)

**C. Grounded claims, compiled graph.** The model never writes ontology. Per document it emits
flat claims in a small task schema, each with a verbatim quote. A deterministic verifier admits a
claim only if the quote is in the document, the value is in the quote, and the relation kind is in
the vocabulary; rejected claims go back once, then are dropped. A resolver merges entities across
documents by key, and a compiler writes the graph with the SDK, placing properties in facets from
the ontology schema. (`pipeline_compiled.py`, arm `c_compiled`.) In one sentence, as an
experiment: *the model extracts quoted facts, a verifier keeps only the ones the text supports,
and a compiler turns them into CASE/UCO; we test whether separating reading from modeling makes
the graph more faithful than letting the model model.*

Why C is shaped this way: the baseline error analysis showed that most of what the model gets
wrong is modeling, not reading. Of A1's unsupported statements, 58% were the right value on the
right entity under the wrong property, and most of the rest were unanchored or invented nodes. A
compiler cannot misplace a property, and a verifier cannot admit a value the text does not
contain. The model is left with the part it is good at.

Planned variants once the three-way comparison is in: C with the reader fine-tuned on a held-out
split of the benchmark (Tinker supports this on the same model), and C with per-document readers
run as separate agents and a critic pass over the compiled graph.

## Measures

Per method, over 100 cases: precision and recall against gold (strict and value scorers), SHACL
validity, unsupported statements by error class, failures (no graph), cost (tokens, wall time).
For A, the same before and after its QA loop. For C, how many claims the verifier rejected and
how many came back admitted after the repair round.

## Paper

Working title options, none of which name the model family:

1. *Constructing Faithful Evidence Graphs: Serializer, Direct and Compiled Methods on a
   100-Case CASE/UCO Benchmark*
2. *Constructing Graphs That Hold to the Evidence*
3. *Constructing Reliable Cyber-Investigation Graphs from Case Documents*

The first is the recommendation: it names the three methods and the benchmark, and "faithful" is
the property measured.

## Results

Filled in from `harness/results/abc-v1/` when the runs finish.
