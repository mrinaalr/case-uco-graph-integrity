"""profile.toml is the one source of the task's tables: the arms' prompt, arm C's target schema and the hook read the
same kinds, properties and keys the reconciler does, and every name in it exists in the SDK's schema."""

from __future__ import annotations

import hashlib

import graphkit
import hook
import pipeline_edc
from reconcile import ontology

SHARED_SHA256 = "8749882f38730144"  # llm.SHARED before the profile existed (Freeze 12)


def test_profile_fits_the_schema():
    assert ontology.validate() == []


def test_prompt_is_unchanged():
    import llm
    assert hashlib.sha256(llm.SHARED.encode()).hexdigest()[:16] == SHARED_SHA256


def test_arms_and_hook_read_the_profile():
    assert pipeline_edc.TYPES == ontology.LITERAL_PROPS == hook.TYPES
    for kind, (dom, rng) in pipeline_edc.KIND_TYPES.items():
        assert dom in ontology.KIND_CLASSES[kind][0] and rng in ontology.KIND_CLASSES[kind][1], kind
    assert hook.KIND_CLASSES == ontology.KIND_CLASSES
    assert hook.PROP_CLASSES == ontology.PROP_CLASSES
    assert hook.ENTAILS == ontology.ENTAILS and hook.SYMMETRIC == ontology.SYMMETRIC
    assert list(graphkit.RELATION_KINDS) == list(ontology.KIND_CLASSES)
