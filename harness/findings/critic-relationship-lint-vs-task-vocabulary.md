# CRIT-V-RELATIONSHIP-LINT flags every relationship whose kind is outside the UCO vocabularies, with no way to declare a task vocabulary

SDK v1.33.0, `mcp_server/critic/canonical.py` (`lint_kind_of_relationship`). Found 2026-10-27.

## What happens

The lint reports a medium finding for every `uco-core:Relationship` whose `kindOfRelationship` is
not in `ObservableObjectRelationshipVocab` or `ActionRelationshipVocab`:

```
kindOfRelationship 'Employed_By' is not in ObservableObjectRelationshipVocab / ActionRelationshipVocab
Recommended: Use a vocabulary member or justify open-vocabulary kind.
```

UCO's `kindOfRelationship` is an open vocabulary, and the SDK's own `relationship_kinds.json`
is the closed list the lint uses. None of the ten kinds this harness's gold graphs use
(`Employed_By`, `Reports_To`, `Holds_Account`, `Owns_Account`, `Located_At`, `Participated_In`,
`Initiated`, `Transferred_To`, `Authorized`, `Communicated_With`) is in it, so a graph with 25
relationships gets 25 findings of the same rule, and the finding count dominates the review (in the
smoke run, 22 to 33 of 46 to 69 open findings per pass).

## Why it matters

When the findings go back to the originating model, the recommended change tells it to rename the
relationship kinds. For a task whose vocabulary is fixed by the caller (an investigation's schema,
a tool's export mapping, or a gold standard) that is a regression the critic requests. The SDK's
own `evaluation/critic` harness patches the lint out for the same reason:

```python
def _suppress_open_vocab_relationship_lint():
    """Charged_With is CASE-domain; open-vocab lint medium blocks true acceptance."""
```

## Suggestion

Let `start_critic_review` take an `allowed_relationship_kinds` list (or read one from the
coverage contract). Kinds in that list are not linted; kinds outside both the UCO vocabularies and
the list keep the finding. With the list, the finding becomes a faithfulness check instead of a
vocabulary preference, and the harness's `wrong_relation` class measures it directly.

The per-rule table in `results/<run>/qa_delta.md` shows what revisions made in answer to this rule
did to precision and recall.
