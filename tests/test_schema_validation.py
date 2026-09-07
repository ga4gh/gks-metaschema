"""Behavioral proof that generated schemas reject unexpected properties.

Unlike the structural checks in test_source_proc_units.py (which assert the
closure *keywords* are emitted), these tests run instances through a real
draft 2020-12 validator and prove that:

* concrete, non-composed classes reject extra properties via
  ``additionalProperties: false``; and
* allOf-composed classes reject extra properties via
  ``unevaluatedProperties: false`` while still accepting the properties
  contributed through the allOf branches.

The allOf case is exercised with a minimal schema run through the real
``YamlSchemaProcessor`` (same code path that generates the cat-vrs recipe
classes). The recipe classes themselves cannot be validated directly today
because their source uses bare, unresolvable ``$ref: CategoricalVariant``
references; test_recipe_closure_preconditions() proves that the two conditions
required for their closure to actually bite are both met on the real classes.
"""

import pytest
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

# A minimal, self-contained schema mirroring the recipe pattern: a concrete
# class composed via allOf from an abstract base plus a local properties block.
SYNTH_SOURCE = """\
$schema: "https://json-schema.org/draft/2020-12/schema"
$id: "https://example.org/schema/synth/synth-source.yaml"
title: Synth
type: object
strict: true
$defs:
  Base:
    maturity: draft
    abstract: true
    type: object
    properties:
      id:
        type: string
    required:
      - id
  Composed:
    maturity: draft
    description: an allOf-composed concrete class
    allOf:
      - $ref: "#/$defs/Base"
      - properties:
          extra:
            type: string
        required:
          - extra
"""


def _validator_for(doc: dict, cls: str) -> Draft202012Validator:
    """A draft 2020-12 validator targeting ``cls`` within a self-contained doc.

    The whole processed document is registered under its ``$id`` so internal
    ``#/$defs/...`` references resolve.
    """
    registry = Resource.from_contents(doc) @ Registry()
    return Draft202012Validator({"$ref": f"{doc['$id']}#/$defs/{cls}"}, registry=registry)


def _errors(doc: dict, cls: str, instance: dict) -> list:
    return list(_validator_for(doc, cls).iter_errors(instance))


# --------------------------------------------------------------------------
# Concrete (non-composed) classes: additionalProperties: false
# --------------------------------------------------------------------------


def test_concrete_class_accepts_valid_instance(gkm_core_processor: YamlSchemaProcessor) -> None:
    valid = {"code": "hgnc:1234", "system": "https://www.genenames.org"}
    assert _errors(gkm_core_processor.for_js, "Coding", valid) == []


def test_concrete_class_rejects_extra_property(gkm_core_processor: YamlSchemaProcessor) -> None:
    invalid = {"code": "hgnc:1234", "system": "https://www.genenames.org", "notAllowed": "x"}
    errors = _errors(gkm_core_processor.for_js, "Coding", invalid)
    assert any(e.validator == "additionalProperties" for e in errors), errors


# --------------------------------------------------------------------------
# allOf-composed classes: unevaluatedProperties: false
# (run a minimal schema through the real processor)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def synth_doc(tmp_path_factory: pytest.TempPathFactory) -> dict:
    fp = tmp_path_factory.mktemp("synth") / "synth-source.yaml"
    fp.write_text(SYNTH_SOURCE)
    return YamlSchemaProcessor(fp).for_js


def test_processor_emits_composition_aware_closure(synth_doc: dict) -> None:
    composed = synth_doc["$defs"]["Composed"]
    assert composed["unevaluatedProperties"] is False
    assert "additionalProperties" not in composed
    # the abstract base must be left open, otherwise its additionalProperties
    # would defeat the composed class's unevaluatedProperties closure
    assert "additionalProperties" not in synth_doc["$defs"]["Base"]


def test_allof_class_accepts_composed_properties(synth_doc: dict) -> None:
    """Properties contributed through the allOf branches (id from the base,
    extra from the local block) are accepted -- proving the closure is
    composition-aware. Plain additionalProperties: false would reject these."""
    assert _errors(synth_doc, "Composed", {"id": "a", "extra": "b"}) == []


def test_allof_class_rejects_extra_property(synth_doc: dict) -> None:
    errors = _errors(synth_doc, "Composed", {"id": "a", "extra": "b", "bogus": "z"})
    assert any(e.validator == "unevaluatedProperties" for e in errors), errors


# --------------------------------------------------------------------------
# Real recipe classes: prove the preconditions for effective closure
# --------------------------------------------------------------------------


def test_recipe_closure_preconditions(
    recipes_processor: YamlSchemaProcessor,
    cat_vrs_processor: YamlSchemaProcessor,
) -> None:
    """The recipe (allOf) classes close correctly iff (1) they emit
    unevaluatedProperties: false and (2) their allOf base is left open. Both
    are asserted here; the behavioral proof of the mechanism itself lives in
    test_allof_class_rejects_extra_property above."""
    for recipe_cls in ("ProteinSequenceConsequence", "CanonicalAllele", "CategoricalCnv"):
        d = recipes_processor.for_js["$defs"][recipe_cls]
        assert "allOf" in d
        assert d["unevaluatedProperties"] is False
    # the allOf base (CategoricalVariant, abstract) must NOT emit
    # additionalProperties, or it would defeat the closure above
    base = cat_vrs_processor.for_js["$defs"]["CategoricalVariant"]
    assert "additionalProperties" not in base
