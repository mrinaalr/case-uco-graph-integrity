# Evidence-Grounded Graph Construction: Evaluating the Semantic Fidelity of Machine-Constructed CASE/UCO Graphs

Written 2026-10-27, revised 2026-11-02 for the hook design and 2026-11-03 for the meaning measure and the selector. Supersedes the arm layout in DIRECTION.md; the critic-loop findings there stand.

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
freeze entry (`harness/FROZEN.md`).

## The design

This repo presents a backward verification hook and tests it on three construction methods. Each
method runs as shipped; the hook reads each method's graphs and is the same for all of them.
Three arms by {baseline, +hook} gives six conditions, on the same 100 cases, PDFs and base model
(Qwen/Qwen3.5-9B on Tinker, temperature 0).

| arm | pipeline | conditions |
|---|---|---|
| A, the SDK as shipped | `pipeline_sdk_agent.py`, arm `a_sdk_agent` | `a_sdk_agent`, `a_sdk_agent+hook` |
| B, direct generation | `pipeline_monolith.py`, arm `b_control` | `b_control`, `b_control+hook` |
| C, EDC | `pipeline_edc.py`, arm `c_edc` | `c_edc`, `c_edc+hook` |

A and B get the same task statement (`llm.SHARED`: model only what the documents state, the core
classes to use, the ten relation kinds). C gets EDC's own prompts, with the same classes and
relation kinds as its target schema.

**A. The SDK as shipped.** A coding agent with the SDK's MCP server follows the SDK's own
workflow: read the evidence, route it and look up classes and recipes, write a serializer with
`CASEGraph`, validate, run the critic loop (deterministic policy), finalize. The harness contributes
a file reader, a "save and run this script" tool, and nothing in the graph. The graph at the
agent's first validation is also scored (`@first_validate`).

**B. Direct generation.** One prompt, the CASE JSON-LD back. No tools, no repair.

**C. EDC.** EDC (Zhang and Soh, 2024) at clear-nus/edc 02aad17, in its target-alignment setting
with its default prompt templates and few-shot examples, no refinement and no schema enrichment.
Per input it extracts open triples, writes a definition for each relation, and canonicalizes each
relation to the target schema: the five most similar schema relations by embedding, then an LLM
choice among them or none. The target schema is the task in CASE/UCO terms: the ten relation
kinds, and `Class.property` for each property of the task classes, each defined from the SDK
registry. Each PDF sentence is one input; EDC leaves chunking to its user. EDC does not type
entities, so a serializer types each entity string by the domain and range of its relations
(most votes, ties to the first), treats identical strings as one entity, writes the string as the
entity's key property (`name`, `addressValue`, `accountIdentifier`, ...), and writes the graph
with the SDK.

## The hook

`hook.py`, applied to every arm's final graph:

1. *Render.* Each edge (each scored triple) becomes one sentence from a template filled with the
   CASE/UCO definitions of its classes and property, from the SDK registry. No LLM. A relation
   reads `S, <class S>, <phrase> O, <class O>.`; a property reads
   `The <property> (<definition>) of S, <class S>, is <value>.`, with ISO date-times in words. A
   subject whose label holds the asserted value is named by its class alone, so no sentence says
   "the name of X is X".
2. *Retrieve.* The sentence is embedded and the top 3 source passages are taken. Passages are the
   sentences of the PDFs the arms read, with document, sentence number and character offsets.
3. *Verify.* A local NLI model labels each (passage, sentence) pair supported (entailment),
   contradicted (contradiction) or not enough evidence (neutral).
4. *Policy.* The edge is kept if any passage supports it, citing the one with the highest
   entailment probability; otherwise it is removed, as its Relationship node or as its value on
   the node and the node's facets.

Per edge, `hook.jsonl` records the triple, the sentence, the three passages with their locations
and verdicts, the edge's verdict and the cited passage. The hook is deterministic apart from its
two models, pinned in `[hook]` of `config.toml`: sentence-transformers/all-MiniLM-L6-v2 at
1110a24 for retrieval, MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli at b3546ea for
NLI.

Hypothesis: checking each edge backward against the source, under CASE/UCO's definitions, removes
unsupported edges from any method's graph at a small cost in true edges.

Ablation: the same hook on the same graphs with the definitions taken out. `labels` keeps the class
and property names (`Oscar Banerjee, a person, is employed by Redfern Components Group, an
organization.`); `plain` keeps no ontology term (`Oscar Banerjee is employed by Redfern Components
Group.`). Scored as `<arm>+hook_labels` and `<arm>+hook_plain`. If the definitions do work, the full
template removes more unsupported edges than `labels` and `plain` at no greater cost in true edges.

## Left hook and right hook

Written 2026-11-03, before any run of the two stages. The hook above (hook-v1) put the definitions in
the NLI hypothesis, which no passage contains, and cannot catch the right value under the wrong
property, since that value is in the text. It is split in two, applied in order:

- *Left hook (fidelity).* Steps 2 to 4 on the plain rendering (no class or property definitions),
  with mail-header runs as one passage and retrieval by the plain rendering. Per edge: supported,
  contradicted or not enough evidence, and the cited passage and its location. Unsupported edges
  are removed.
- *Right hook (semantics)*, on the edges the left hook kept. Deterministic checks from the SDK's
  schema and registry (domain, range, datatype, cardinality; the ten relation kinds' domain and
  range from the task statement, since CASE/UCO does not define them; no self-loops), each
  reporting the edges it judged and skipped. Then contrast: the edge must not be outranked on its
  supporting passage by another reading the ontology allows for the same entities, with the
  definitions of the readings in the premise, never in the hypothesis. The margin is tuned on
  `data_dev` only.

Conditions: each arm as built, `+left`, `+right` (on every edge, for ablation) and `+lr`.

Hypothesis: the two stages together remove unsupported and mis-modeled edges from any method's
graph at a small cost in true edges, and the right hook adds a gain the left hook alone does not.

Success criteria:

- The right hook removes wrong-property (`misplaced_property`) and wrong-relation edges the left
  hook keeps.
- Little or no added cost in true edges, and no drop in citation accuracy.
- Left+right beats left alone on value precision for every arm.

## Rendering fixes

Written 2026-11-03, after the rendering audit (Results, "Rendering audit") and before any run of the fixes. The
audit found readings the plain rendering does not keep apart. Three fixes to the right hook, each run on `data_dev`
on its own, in this order, then the templates are frozen:

- *Header rule.* A message's mail-header block decides its edges by rule, not NLI: the `Date:` line is the time it
  was sent (RFC 5322's origination date), so a sentTime must equal it and a receivedTime that equals it fails;
  a sender must be on the `From:` line and a recipient on the `To:` line. Edges with no header block for their
  message are skipped and left to contrast. The rule's verdict and the line it read are recorded per edge.
- *Issuer template.* accountIssuer renders as an event ("⟨issuer⟩ issued account ⟨N⟩") instead of "The account
  issuer of N is ⟨issuer⟩".
- *Entailed competitors.* Contrast compares only readings that cannot both be true. A competitor the edge entails
  (Initiated and Authorized each entail Participated_In) is not one.

Success criteria:

- Header rule: the right hook removes all 20 planted receivedTimes the left hook keeps on the corrupted dev graphs,
  and removes no more true dev gold edges than under Freeze 9 (14).
- Issuer template, kept only if all hold: in the audit, more accountIssuer edges outrank Owns_Account and the
  median margin does not fall; Owns_Account against accountIssuer does not get worse; the left hook keeps at least
  as many true dev gold accountIssuer edges.
- Entailed competitors: no planted edge `+lr` removed before is kept after, and no more true dev gold edges are
  removed.

## Meaning

Written 2026-11-03, after the rendering fixes and before the selector. Precision and recall count edges; the
research question is whether the graph, read under CASE/UCO, means what the evidence means: it says nothing the
evidence does not (soundness) and says what the evidence states (completeness). `meaning.py` measures that with
competency questions, generated from each gold graph and asked of the gold graph and of the graph under test alike.

- A question starts from an entity's key value (a person's name, an address, an account number, a message's
  subject, an event's type), as a query by value would, and follows one or two steps out of or into the entity.
  Its answer is a set of literal values or entities, an entity named by its key.
- 1-hop: one fact. "Who owns account 2622357143?", "When was 'Quarter-end vendor payments' sent?"
- 2-hop: two steps through an intermediate entity. "Which organization employs the sender of message M?" A split,
  merged or misdirected entity breaks the path.
- Each side starts from every entity of a compatible class whose literals hold the value, and answers match under
  the value scorer's rules. Owns_Account and AccountFacet.owner are one fact; Communicated_With is symmetric.
- Per question: answer recall, answer precision, and exact (every gold answer found, nothing else). Micro over
  questions. A gold graph scored against itself is exact on every question.

## Ontology selector

Written 2026-11-03, after the first meaning scores (Results, "Meaning") and before any test run of the selector.
The hook decides only the edges a method wrote, and only by keeping or removing them. `selector.py` decides every
reading the task's ontology allows for the entities a graph names: the ontology lists the readings, the source picks.

1. *Identity.* Entities of one class with one key are merged.
2. *Anchoring.* Each entity is placed in the passages that contain its key (no times). Mail-header runs are one
   passage.
3. *Readings.* For each pair of entities that share a passage or an edge, the relation kinds and object properties
   whose domain and range fit, either direction (the right hook's readings).
4. *Selection.* Each reading's plain sentence is scored by NLI on the pair's shared prose passages and the passages
   its edges retrieve, with the definitions of the properties in play in the premise. A reading is selected when NLI
   labels it entailment on some passage and no reading that cannot hold with it outranks it by more than the
   contrast margin. Mail headers are read by rule: the right hook's header rule for a message's sender and
   recipients, and Communicated_With between two people when a message goes from one's address to the other's.
   A selected reading no edge states is added (recovery); one that replaces a stated edge is a repair. A reading
   the method did not state needs entailment of at least `add_threshold` (0.9) on a passage both entities share.
5. *Literals.* A value must occur in a passage that names its subject, else be supported by the left hook. A
   date-time in a form xsd:dateTime rejects is rewritten in ISO form when it parses; a receivedTime that is the
   Date: line becomes the sentTime; a literal whose property loses contrast moves to the winning property.
6. *Cardinality.* A property CASE/UCO allows once keeps one value only when its score leads the next by more than
   the contrast margin; otherwise none, recorded as an abstention. Spellings of one value keep the one the source
   uses.

The selector adds no entity, and no literal beyond a message's header facts. Its rows record each reading decided,
by NLI or by rule, with its passage, and each edge removed or added with the reason.

Dev arms (`selector_dev.py`, `data_dev`): the 20 gold graphs, their corrupted copies (`hook_dev_check.py`), the gold
graphs with 30% of their object edges removed (`dropped`, seed 0: a method that missed them), and C's graphs on 5
dev cases. Changes made on dev, in order, each after reading dev output: literals anchored beside their subject
(rotated startTimes were kept because the value occurs elsewhere); a reading another selected reading entails is
dropped; header passages read by rule, not NLI (NLI read two recipients of one message as having communicated);
the issuer said as an event; single-valued properties decided by contrast advantage (merges left two names, which
failed SHACL).

Success criteria for the one test run, on A and B, written before it: the selector's graphs answer more 1-hop and
more 2-hop questions exactly than both the method's graph and the method's graph after the hook (hook-v1), and their
value precision is no more than 5 points below the method's graph.

## Reconciler

Written 2026-11-05, after the selector's test run and before any dev run of the reconciler. The hook and the
selector each edit a graph in place, decide as they score, and keep or remove only (the selector also adds links
between entities the graph already names). The test results show what that buys: precision rises and meaning falls,
on both arms. `harness/reconcile/` keeps the mechanics and changes the shape: a graph is read into a ledger of
claims, every pass only adds to a claim's record, and a policy decides from the record. Whoever built the graph is
irrelevant to every module (tests/test_layering.py: no construction arm on the import path, no gold file named).

1. *Ingest.* The graph's scored triples become `stated` claims; each keeps the node that stated it.
2. *Verify* (pass 1, backward). Each claim's plain sentence against the source: the top 3 passages by the hook's
   embedder, each labelled by its NLI model, as evidence rows; a literal found verbatim beside its subject, and a
   pair of entities named in one passage, as span evidence. Nothing is decided. Modality (asserted, reported, hedged,
   negated) is read from the best supporting passage by a word list and recorded, never used.
3. *Propose* (pass 3, forward). Candidates the graph may lack, as `proposed` claims: every reading the profile allows
   for a pair of entities that share a passage or an edge (the selector's enumeration), a repair of the graph's own
   link where it has one; a message's time, sender and recipients from its mail header; an ISO form of a stated time
   that xsd:dateTime rejects, a repair of it; and the facts an LLM lists from each document (`propose_llm.py`, cached
   per case), with values admitted only as exact spans and names resolved to entities, or, for a person, organization,
   account or address, to a provisional entity that enters only with a link that passes (an event, message or
   location is described, not named, and is not proposed new). Entities of one class and one key are merged first.
   Every proposal then gets the same evidence a stated claim gets.
4. *Readings* (pass 2, semantics). On every claim with support, stated and proposed together: the right hook's
   checks (domain, range, datatype, self-loop; cardinality, where a proposed value displaces a stated one only by more
   than the margin), the header rule, and contrast against the readings that cannot hold with the claim. A wrong
   stated edge and its right reading are thus decided from the same passages.
5. *Decide.* Five verdicts from the record alone: `malformed` (a check failed; a literal the class declares on its
   own facet, an EmailMessage's subject, is not malformed for sitting on the node), `contradicted` (the header rule
   says otherwise, or a competitor outranks it by more than the margin on every supporting passage; an NLI
   contradiction label alone is recorded and contradicts nothing), `ambiguous` (supported, but a rival is entailed
   within the margin on its best passage), `supported`, `insufficient` (no passage supports it; unverified, not
   false). A proposal is `supported` only at the bar: entailment of at least `add_threshold` on a prose passage both
   entities share, the header rule, or a literal beside its subject; a repair is written only when the claim it
   repairs is removed; a reading a stated claim entails is not added. Policies: `conservative` removes `contradicted`
   and `malformed` and flags `insufficient`; `strict` removes `insufficient` too, except an entity's key; `hook-v1`
   and `lr` reproduce the hook.
6. *Emit.* The input graph byte for byte, the reconciled graph (removals, merges, additions applied to the input;
   nothing else touched), the ledger (claims, entities, decisions) and `provenance.jsonld`: the run as a
   `case-investigation:InvestigativeAction`, each removal and addition as a `uco-core:Assertion` with its statement,
   verdict, reason and passage.

The task's tables (the ten kinds with domain and range, the task's properties, each class's key, the narrowed ranges
of `accountIssuer`, `from` and `to`) move to `harness/profile.toml`, read by every arm, the hook and the reconciler,
and checked against the SDK's schema at load; the arms' prompt is byte-identical (tests/test_profile.py).

Parity, before any new number: the published hook decided from the ledger (`--policy hook-v1 --template full
--passages sentence --query rendered`) keeps the same edges as hook-v1 on 1,226 of 1,226 edges of B (19 cases with a
graph) and 417 of 417 of A (6 cases); the left and right hooks (`--policy lr`) keep the same edges as fix-dev `+lr` on
1,559 of 1,559 edges of dev gold, 1,760 of 1,760 of the corrupted copies and 139 of 139 of C's five dev graphs
(`PYTHONHASHSEED=0`, MPS).

Success criteria for the dev run (`rec-dev`, `data_dev`; gold, corrupted, dropped, C on 5 cases, and A and B as
built on dev), written before it:

- Not degrading: on dev gold, `conservative` removes at most 1% of true edges (the left and right hooks removed 8.7%)
  and keeps 2-hop exact at or above 0.95 (`+lr`: 0.741).
- Corrupted: `strict` reaches value precision of at least 0.90 and recall of at least 0.75 (`+lr`: 0.947 / 0.611;
  `+sel`: 0.896 / 0.781), and answers more 1-hop questions exactly than `+sel` (0.709).
- Dropped: `conservative` recovers at least 60% of the removed object edges (`+sel`: 176 of 241).
- Calibration (`calibration.py`): on corrupted graphs, at least 90% of the stated claims called `contradicted` are
  edges gold does not support; on gold, no stated claim is called `contradicted`.
- B on dev: `strict` answers more 1-hop questions exactly than B as built (0.494) and B+sel (0.462), at value
  precision of at least B+sel's (0.665).

Disclosures:

- The LLM proposals are PR #11's cache (`results/llm-dev/proposals`, Qwen/Qwen3.5-9B on Tinker, one call per
  document), reused unchanged; `propose_llm.py` regenerates them with the same prompt less the document's kind,
  which came from gold. No new model call was made for this work.
- hook.py now reads its tables from profile.toml and no longer imports arm C; the hook-v1 parity above is the
  check that its behaviour did not change. score.py, meaning.py and generate_data.py are byte-identical to Freeze 12.
- The reconciler copies the scorer's key and grounding rules (reconcile/keys.py) rather than importing them;
  tests/test_ledger.py holds the two to agreement on dev. The evaluator and the method under test share no code.
- The design was set before the dev run; the stub-verifier smoke runs on dev case_01 and case_02 found two
  structural faults that were fixed before it (a normalized time written beside its original; a literal alternative
  able to displace a true value in cardinality), both now covered by tests.
- The dev run was run twice. The first (`results/rec-dev1`) missed most criteria: on gold, `conservative` removed 20
  true edges (1.3%) and added 92 false ones; B's 1-hop exact fell from 0.494 to 0.416 under `conservative` and 0.398
  under `strict`. Reading the ledgers gave five faults, each a rule, not a threshold: (1) the same value proposed
  under a sister property (region beside postalCode) outranked the true value under NLI, removed it by contrast and
  was written in its place, 11 of the 20 true removals and 27 of the 92 additions; (2) an NLI contradiction label on
  a passage naming the claim's entities counted as a contradiction with no support to weigh it against, 5 true
  removals (an issuer read as an owner, an alias read as a denial); (3) a reading of a pair the graph already linked
  correctly was added beside the link (Authorized beside Performed), 17 false additions and 3 true ones across all
  arms; (4) an address the LLM wrote in full did not resolve to the location keyed by its street, and events,
  messages and email accounts entered as provisional duplicates, 45 of the 92 additions on gold and every provisional
  entity of those classes false on every arm; (5) a literal B writes on the node that the schema declares on the
  node's facet (an EmailMessage's `subject`, `sentTime`) failed the domain check and was removed, 24 true edges and
  with them the keys B's questions start from; (6) `strict` removed unverified keys, leaving entities nothing aligns
  to (corrupted, `strict`: value precision 0.897, strict-scorer precision 0.583). The hook policies keep the hook's
  behaviour on each point (parity re-run below). The fixes were made after seeing dev numbers; the test criteria
  stand as written.
- The 100-case test run needs a GPU and is not part of this work: every number here is dev. The criteria for a test
  run are the dev criteria above, with the selector's test numbers (`sel-test`) in place of the dev ones.
- Modality is recorded and unmeasured: the benchmark's documents contain no hedged or reported statement.

## Related work

- [SPIRES](https://doi.org/10.1093/bioinformatics/btae104) (Caufield et al., 2024) has an LLM fill
  a user-defined schema from text and links what it extracts to ontology identifiers; it grounds
  terms in an ontology, where the hook grounds edges in the source text.
- [EDC](https://aclanthology.org/2024.emnlp-main.548) (Zhang and Soh, 2024) is arm C: it
  canonicalizes extracted relations forward to a schema, where the hook checks each finished edge
  backward against the source.
- [GraphRAG](https://arxiv.org/abs/2404.16130) (Edge et al., 2024) builds an entity graph from text
  with an LLM as an index for query-focused summarization; its graph serves retrieval, not a record
  that must be true to the source.
- [Text2KGBench](https://arxiv.org/abs/2308.02357) (Mihindukulasooriya et al., 2023) benchmarks
  ontology-driven graph generation from text against gold facts, with measures of ontology
  conformance and hallucination; this benchmark does the same for CASE/UCO, with each gold
  statement tied to the sentence that states it.
- [ProVe](https://arxiv.org/abs/2210.14846) (Amaral, Rodrigues and Simperl, 2022) checks a Wikidata triple
  against the web page cited as its provenance: text extraction, triple verbalisation, sentence selection, claim
  verification by an entailment model, then one binary verdict, supported or not. The reconciler's first pass is
  that pipeline on a CASE/UCO graph; it differs after it: the verdict is one of five, the ontology's other readings
  are scored beside the claim, and what the source states and the graph lacks is proposed and held to the same
  check. [GraphEval](https://arxiv.org/abs/2407.10793) (2024) turns an LLM's output into triples and checks each
  against the context with NLI, to find hallucinations; the same check, on text rather than a graph.
- [PERSEUS](https://ceur-ws.org/Vol-4246/llms4kgoe-5.pdf) validates each LLM-extracted triple by
  NLI entailment against retrieved source evidence, as the left hook does, on open-schema triples.
- [Sainz et al., 2021](https://aclanthology.org/2021.emnlp-main.92) extract relations by scoring
  a verbalization of each candidate relation with an entailment model; the selector's selection
  step does the same over the readings CASE/UCO allows, on a finished graph.
- [OAK+MEND](https://arxiv.org/abs/2605.29168) (2026) corrects a finished graph after extraction:
  it detects ontology violations (type, domain, range) and has an LLM pick a fix. It targets
  consistency with the ontology; the selector also replaces edges that are consistent but not what
  the source says (an owner written as an issuer).
- [KGCQual](https://arxiv.org/abs/2607.10212) (2026) scores whether extracted triples preserve
  the semantics of their source sentence; [BIGS](https://semantic-web-journal.net/content/evaluating-knowledge-graph-construction-text-without-supervision)
  (under review) compares verbalized triples with the source in both directions; [Mousavi et
  al., 2024](https://aclanthology.org/2024.lrec-main.335) use regeneration between graph and text
  as a proxy for their equivalence. All work on open-schema triples; the meaning measure here asks
  questions of a graph under a formal ontology, against gold.
- [Dušek and Kasner, 2020](https://aclanthology.org/2020.inlg-1.19) check data-to-text output
  with NLI in both directions, for hallucinations and omissions; QAGS ([Wang et al.,
  2020](https://aclanthology.org/2020.acl-main.450)) scores a summary's faithfulness by asking the
  same questions of it and of its source. The meaning measure applies the question approach to a
  graph.

## Disclosures

- The relation phrases are author-written. CASE/UCO does not define the ten relation kinds, so the
  hook's template says each kind with a phrase written for this repo (`RELATION_PHRASES` in
  `graphkit.py`; `Employed_By` is "is employed by", `Holds_Account` is "holds"). C's target schema
  defines each kind with the same phrase.
- C's embedder is swapped. EDC's default, intfloat/e5-mistral-7b-instruct (14 GB), does not fit the
  machine the runs use; C uses the hook's all-MiniLM-L6-v2. EDC accepts any sentence transformer.
- C runs with two fixes in its adapter; the submodule is unchanged. `edc_framework.py:270` logs a
  variable that is unset when a run's first input yields no triples, so EDC raised
  `UnboundLocalError`; before the fix, a probe of each benchmark case's first sentence found about
  12 of 100 cases that would crash. The base model often
  replies with tuples, `[('a', 'b', 'c')]`, which EDC's parser drops whole; before the fix 22.3% of
  input sentences were lost this way and 31.8% yielded no triples, after it 9.5% (148 sentences,
  6 test cases). The other adaptations: LLM calls go to the harness endpoint, an empty reply is
  read as no choice, and a schema-retriever training module EDC does not call here is stubbed.
- C's serializer writes edges EDC does not state: each entity's class, and its name or identifier
  taken from the entity string. Each case lists them (`adapter_edges.json`), and C is also scored
  without them (`c_edc@no_adapter`: the same alignment, those edges left out of every count).
- Header limitation. Gold states each email header fact on its own line (`Date: ...` for
  `sentTime`, `To: ...` for `to` and `Communicated_With`), and the line names neither the message
  nor the sender, so no single-sentence passage entails the edge. The hook removes many of these
  true edges.
- Dev ceiling. On 8 dev gold graphs (613 edges, all true) the hook keeps 88.7%. The losses are
  `Communicated_With` (23% kept), `sentTime` (29%), `to` (35%) and `Located_At` (65%; gold states
  these indirectly, "took place at the Stonebridge Services Group office"); every other property
  keeps more than 80%.
- The NLI model keeps an edge from an entity to itself ("x holds x") whenever a passage names it:
  all 3 such edges from C in testing. A false positive the hook does not catch.
- Some registry definitions read wrong for this use, and the hook uses them as written:
  `observable:from` and `observable:to` on an email message are defined as a phone number.
- A and B are not rerun: their abc-v1 outputs (Freeze 5) are scored here. The pipelines are
  byte-identical, the prompt and document text are the same, and every run used SDK v1.33.0 and
  Qwen/Qwen3.5-9B. C runs fresh.
- The selector's test run was restarted once. The first start, under an earlier version, was
  stopped to fix single-valued properties that failed SHACL (two names after a merge, a repair onto
  a filled property); none of its outputs was scored or read, and they were deleted. The fix and
  the run are under Freeze 12.
- The meaning scores of A, B and their hook-v1 graphs on the test set were computed before the
  selector's design was final, and informed it: they showed the hook lowers meaning there.
- The selector says an account's issuer as an event ("X issued account N"), the template the
  rendering fixes tried for the hook and did not keep, since the left hook then kept fewer true
  issuer edges. In the selector both readings of the pair are scored on the same passages, and on
  dev corrupted case_01 to case_05 the template raised value precision from 0.888 to 0.893.
- The selector's Communicated_With header rule (a message from one person's address to the
  other's) is the reading of a mail header the benchmark's gold uses: gold states Communicated_With
  on the To: line.
- `add_threshold` (0.9) was set before the first dev run and not tuned.
- The selector's dev arms are not independent of its design: every change listed under "Ontology
  selector" was made after reading dev output.

## Data splits

- `data/`: the 100 benchmark cases (seed 20251025). Test only.
- `data_dev/`: 20 cases (seed 20260101) for prompt and pipeline tuning.
- `data_train/`: 200 cases (seed 20260202), unused in this design.

## Measures

Per condition, over 100 cases: precision and recall against gold (strict and value scorers),
validation pass rate (`case_validate`), unsupported statements by error class, failures (no
graph), cost (tokens, wall time). For each +hook condition: the edges removed, how many of them
gold supports (true edges removed), the share of unsupported edges removed, and for each kept true
edge whether its cited passage is the sentence gold states it in. For C, the same without the serializer's own edges. Grounding, without
reference to gold: the share of emitted assertions found in the source text, and the grounded x
gold-supported cells. For A, the graph at its first validation too. Meaning: competency
questions answered exactly, with answer recall and precision, 1-hop and 2-hop. For each +sel
condition: edges removed, repaired and recovered, and single-valued properties kept or abstained.

## Paper

Title: *Evidence-Grounded Graph Construction: Evaluating the Semantic Fidelity of Machine-Constructed
CASE/UCO Graphs*. The question: does a machine-built graph, read under CASE/UCO, mean what the
evidence means, and does checking the finished graph against its source move it there, whichever
method built it (A, B, C)? Two checks: the hook, which keeps an edge only if a passage supports it,
and the selector, which lets the ontology list the readings and the source pick. Reliability is
validity and failure rate; fidelity is precision and recall against the gold graph with the
error-class breakdown, and meaning; for the hook, true edges removed and citation correctness.

## Results

C's 100-case run is not done yet.

Ablation, run hook-v1 (Freeze 6): the hook and its two ablation templates on the 100 abc-v1
graphs of A and B. Precision and recall are micro. The hook columns (true and unsupported edges
removed, kept true edges citing the gold sentence) are under the strict scorer.

| condition | valid | P strict | R strict | P value | R value | true removed | unsupported removed | cite correct |
|---|---|---|---|---|---|---|---|---|
| A | 35 | 0.371 | 0.139 | 0.506 | 0.184 | | | |
| A+hook | 39 | 0.376 | 0.108 | 0.547 | 0.153 | 17.5% | 26.7% | 75.1% |
| A+hook_labels | 38 | 0.339 | 0.103 | 0.520 | 0.154 | 15.3% | 20.9% | 82.9% |
| A+hook_plain | 40 | 0.358 | 0.100 | 0.550 | 0.150 | 17.4% | 29.5% | 78.0% |
| B | 91 | 0.270 | 0.219 | 0.595 | 0.476 | | | |
| B+hook | 93 | 0.277 | 0.191 | 0.632 | 0.432 | 10.1% | 16.4% | 66.8% |
| B+hook_labels | 93 | 0.264 | 0.180 | 0.634 | 0.428 | 12.5% | 17.2% | 77.9% |
| B+hook_plain | 93 | 0.268 | 0.181 | 0.631 | 0.422 | 12.9% | 18.1% | 68.1% |

The hook trades recall for precision, by a few points. With the full template, value precision
rises 4.2 points on A and 3.7 on B, recall falls 3.1 and 4.4, and 4 more A graphs and 2 more B
graphs validate. It separates unsupported from true edges only weakly: it removes 26.7% of A's
unsupported edges and 17.5% of its true ones (B: 16.4% and 10.1%).

The definitions show no consistent effect. `plain` removes more unsupported edges than the full
template on both arms (29.5% against 26.7% on A, 18.1% against 16.4% on B), at the same cost in
true edges on A and a higher one on B. The full template has the highest strict precision on both
arms and keeps the most true edges on B. The precision gaps between templates are under 4 points,
from one run with no significance test. The definitions lower citation accuracy: with class and property names but no
definitions, 82.9% (A) and 77.9% (B) of kept true edges cite the gold sentence, against 75.1% and
66.8% with them.

On this benchmark, this NLI model and this embedder, the effect comes from checking each edge
backward against the source, not from the CASE/UCO definitions in the sentence.

### Left and right hooks

Six conditions on the 100 cases: pending the GPU run.

Dev, under Freeze 9 (contrast margin 2.0 in log-odds, chosen on dev case_01 to case_10): the 20 dev gold
graphs, `hook_dev_check.py`'s corrupted copies with planted wrong-property and wrong-relation edges, and C's
graphs on 5 dev cases. Value scorer; intervals are the bootstrap 95% over cases. Each cell is `+left` / `+lr`.

| sample | P value | R value | true edges removed by the right hook | planted wrong property kept | planted wrong relation kept | kept true citing gold | valid |
|---|---|---|---|---|---|---|---|
| dev gold | 0.987 / 0.985 | 0.924 / 0.913 | 14 of 1,459 | | | 86.4% / 86.2% | 20 / 20 |
| dev corrupted | 0.822 (0.807-0.838) / 0.928 (0.914-0.943) | 0.621 / 0.611 | 14 of 981 | 59 / 20 of 80 | 94 / 10 of 202 | 80.0% / 79.8% | 0 / 15 |
| C, 5 dev cases | 0.651 (0.532-0.776) / 0.670 (0.552-0.800) | 0.186 / 0.170 | 2 of 62 | | | 65.8% / 64.9% | 1 / 5 |

The left hook keeps 93.6% of the true dev gold edges. An entity with no literal of its own (a gold email
account) is named by the address it links to; named by its IRI, the left hook kept 83.4%. The account's
`emailAddress` edge then reads close to a tautology and is checked only weakly.

The right hook removes most of the planted edges the left hook keeps: every accountIdentifier written as a name,
street written as locality, Employed_By and Located_At reversed; 19 of 20 Initiated written as Authorized; 17 of
20 owners written as issuers; 15 of 21 swapped senders and recipients. It removes none of the 20 sentTimes
written as receivedTime: the NLI model does not separate the two on a `Date:` line. On C it removes malformed
times (`13:10:00` as a dateTime), a person typed against Employed_By's domain and an inverted Holds_Account, and
two true address parts that contrast reads as the locality; one of those is a Location's street, its alignment
key, so the scorer loses its other edges too, which is most of C's drop in recall. Of 2,575 edges the right hook
keeps, 1 cites a different passage than the left hook; the small drops in citation accuracy come from which true
edges it removes.

### Rendering audit

The hook's NLI step can only separate readings its sentences separate. A dev-only diagnostic, run after the dev
results above with no success criterion set beforehand (`rendering_audit.py`, Freeze 10): for each true dev gold
edge with a confusable reading, the plain sentence of the edge and of the competitor, scored against the passage
that states the edge with the right hook's premise. Margin is log-odds(true) - log-odds(competitor); the right hook
removes a true edge below -2.

| true | competitor | n | true ranked higher | median margin | margin < -2 |
|---|---|---|---|---|---|
| sentTime | receivedTime | 39 | 0/39 | -0.92 | 0 |
| accountIssuer | Owns_Account | 56 | 46/56 | +4.40 | 3 |
| Owns_Account | accountIssuer | 40 | 40/40 | +2.04 | 0 |
| Initiated | Participated_In | 114 | 93/114 | +1.21 | 0 |
| Initiated | Authorized | 114 | 114/114 | +3.15 | 0 |
| Authorized | Initiated | 9 | 9/9 | +6.55 | 0 |
| Authorized | Participated_In | 9 | 9/9 | +2.50 | 0 |
| Participated_In | Initiated | 17 | 17/17 | +13.51 | 0 |
| Participated_In | Authorized | 17 | 17/17 | +10.51 | 0 |
| Holds_Account | Owns_Account | 93 | 93/93 | +6.75 | 0 |
| Reports_To | Communicated_With | 8 | 8/8 | +1.13 | 0 |
| Reports_To | Reports_To reversed | 8 | 8/8 | +8.08 | 0 |
| Communicated_With | Reports_To | 53 | 53/53 | +9.21 | 0 |
| Communicated_With | Reports_To reversed | 53 | 53/53 | +10.66 | 0 |
| Transferred_To | Transferred_To reversed | 3 | 3/3 | +10.87 | 0 |

NLI ranks receivedTime above sentTime on every `Date:` line, by a small margin; this is why the right hook keeps
every planted receivedTime. The line does not say "sent", and the definitions in the premise do not settle it. The
ten issuers ranked below Owns_Account are all on "account N at Bank X is registered to Person". The Initiated
losses are on "started the ...", which entails participating, so the competitor is not a wrong reading. The other
relation kinds separate by wide margins. Employed_By and Located_At have no competing reading the task allows and
are not tested.

### Rendering fixes

Dev, Freeze 9 against Freeze 11 (see "Rendering fixes" above for the criteria, written before these runs): the 20
dev gold graphs, their corrupted copies and C's graphs on 5 dev cases, `+lr`, value scorer under PYTHONHASHSEED=0.

| sample | P value | true edges removed by the right hook | planted receivedTime kept | swapped sender or recipient kept | planted wrong property kept | planted wrong relation kept | valid |
|---|---|---|---|---|---|---|---|
| dev gold | 0.985 / 0.985 | 14 / 14 of 1,459 | | | | | 20 / 20 |
| dev corrupted | 0.928 (0.914-0.943) / 0.947 (0.933-0.962) | 14 / 14 of 981 | 20 / 0 of 20 | 6 / 5 of 78 | 20 / 0 of 80 | 10 / 9 of 202 | 15 / 15 |
| C, 5 dev cases | 0.670 / 0.670 | 2 / 2 of 62 | | | | | 5 / 5 |

- Header rule: criteria met. It removes all 20 planted receivedTimes and removes no true dev gold edge; on dev gold
  it passes 91 edges and fails none. Replies in a thread share a subject, so where their header blocks disagree on a
  sender or recipient it skips (10 dev gold edges, and the 5 swapped plants still kept). It judges none of C's
  edges: C's dev graphs give each message its date as its subject and no sender or recipient.
- Issuer template: not kept. In the audit it ranks the issuer above Owns_Account on 56 of 56 (from 46), but
  Owns_Account against the issuer falls to 39 of 40, and the left hook keeps 31 of 56 true issuer edges (from 46):
  NLI does not read "account N at Bank X" as "Bank X issued account N".
- Entailed competitors: criteria met, with no change to `+lr` on dev. In the audit, 123 pairs (Initiated and
  Authorized against Participated_In) are no longer compared; the `+right` ablation catches 2 fewer wrong-entity
  edges.

### Meaning

The 100 test cases, A and B as built and after hook-v1 (Freeze 6 graphs; meaning.py under Freeze 12). 7,529 1-hop
and 15,606 2-hop questions. Exact: every gold answer found and nothing else.

| condition | 1-hop exact | 1-hop answer recall | 1-hop answer precision | 2-hop exact | 2-hop answer recall | 2-hop answer precision |
|---|---|---|---|---|---|---|
| A | 0.150 | 0.160 | 0.863 | 0.088 | 0.100 | 0.828 |
| A+hook | 0.116 | 0.122 | 0.863 | 0.055 | 0.064 | 0.812 |
| B | 0.498 | 0.540 | 0.939 | 0.394 | 0.471 | 0.923 |
| B+hook | 0.448 | 0.477 | 0.943 | 0.297 | 0.343 | 0.926 |

The hook lowers meaning on both arms. The answers A and B give are mostly right before it (answer precision 0.86
and 0.94); most questions fail on answers the graph does not hold (answer recall 0.16 and 0.54). The hook cannot
add an answer, and each true edge it removes breaks the questions that reach it, a 2-hop question at either step.

On dev, where the corrupted graphs give wrong answers, the hook does what it is for: answer precision on 1-hop
questions rises from 0.515 to 0.938 (`+lr`), and every edge it keeps cites the passage that supports it.

### Ontology selector, dev

Freeze 12, `data_dev`, value scorer. Each cell is the graph as given / `+lr` / `+sel`.

| sample | P value | R value | 1-hop exact | 2-hop exact | valid |
|---|---|---|---|---|---|
| C, 5 dev cases | 0.545 / 0.670 / 0.580 | 0.191 / 0.170 / 0.209 | 0.086 / 0.073 / 0.107 | 0.016 / 0.012 / 0.065 | 1 / 5 / 5 |
| dev gold | 1 / 0.985 / 0.963 | 1 / 0.913 / 0.933 | 1 / 0.877 / 0.883 | 1 / 0.741 / 0.824 | 20 / 20 / 20 |
| dev corrupted | 0.600 / 0.947 / 0.896 | 0.677 / 0.611 / 0.781 | 0.375 / 0.380 / 0.709 | 0.316 / 0.155 / 0.671 | 0 / 15 / 13 |
| dev dropped | 0.990 / 0.987 / 0.966 | 0.837 / 0.773 / 0.897 | 0.722 / 0.645 / 0.824 | 0.477 / 0.367 / 0.720 | 20 / 20 / 20 |

The hook has the higher precision on every sample; the selector the higher recall and the more questions answered
exactly, on every sample.

- Corrupted: the selector adds 130 true edges in place of wrong ones (66 false) and 194 true edges no edge stated
  (43 false).
- Dropped: of the 241 object edges taken out, it recovers 176, with 33 false recoveries and 25 false repairs.
- Gold: it loses 98 of 1,459 true edges (the hook 127) and adds 65 false ones. 20 of the removals are
  accountIssuer abstentions: the bank and the account's owner both read as the issuer, by less than the margin.
- C: it adds 15 true edges and 27 false. The false additions read by hand are true of the source but land on
  entities C wrote wrong (a person named by an email address, a first name alone); the selector adds no entity.

### Ontology selector, test

Freeze 12, the 100 test cases, run once. A and B as built (abc-v1), after hook-v1 and after the selector. Value
scorer; meaning over 7,529 1-hop and 15,606 2-hop questions.

| condition | P value | R value | 1-hop exact | 2-hop exact | valid | failures |
|---|---|---|---|---|---|---|
| A | 0.506 | 0.184 | 0.150 | 0.088 | 35 | 50 |
| A+hook | 0.547 | 0.153 | 0.116 | 0.055 | 39 | 50 |
| A+sel | 0.581 | 0.163 | 0.127 | 0.066 | 42 | 50 |
| B | 0.595 | 0.476 | 0.498 | 0.394 | 91 | 2 |
| B+hook | 0.632 | 0.432 | 0.448 | 0.297 | 93 | 2 |
| B+sel | 0.648 | 0.437 | 0.449 | 0.303 | 93 | 3 |

The success criteria are not met. The selector's graphs answer more questions exactly than the hook's on both arms,
but fewer than the method's own graph: 1-hop 0.127 against 0.150 on A, 0.449 against 0.498 on B. The precision
criterion holds, and the selector's precision is the highest of the three on both arms (A 0.581, B 0.648).

On real method output the selector acts mostly as a stricter hook. On B it removes 942 of 5,976 edges, repairs 82
and recovers 33; on A it removes 674 of 2,793, repairs 63 and recovers 35. What it can add is bounded by what the
method wrote: of the gold facts B's graphs miss, 377 of 3,745 (10%) are relations between two entities B wrote, the
only kind the selector recovers; 2,062 are literals and 1,306 are relations to an entity B did not write. On A, 205
of 2,287 (9%). The dev arms built from gold graphs keep every entity, and their errors are the kind the selector
fixes, so dev overstates it.

B case_60 is a new failure: the selector raised `KeyError` on a Relationship node
(`rel-person-luca-haddad-person-owen-park`), and the case counts as no graph.
