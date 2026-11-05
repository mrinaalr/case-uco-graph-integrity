"""Reconcile any CASE/UCO graph against its source documents, whoever built the graph.

The graph is read into a ledger of claims (ingest), each claim is checked backward against the source (verify), the
readings the ontology allows for the same entities are scored beside it (readings, checks, contrast), facts the
source states and the graph lacks are proposed and held to the same checks (propose), a policy turns each claim's
record into a verdict (policy), and the reconciled graph is written next to the original with every decision
(emit). No module here imports a construction arm or reads a gold file (tests/test_layering.py)."""
