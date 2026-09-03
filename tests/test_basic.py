import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest
import yaml
from ga4gh.gks.metaschema.scripts.source2classes import main as s2c
from ga4gh.gks.metaschema.scripts.source2splitjs import split_defs_to_js
from ga4gh.gks.metaschema.scripts.y2t import main as y2t
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

root = Path(__file__).parent

processor = YamlSchemaProcessor(root / "data/vrs/vrs-source.yaml")
processor.js_yaml_dump(open(root / "data/vrs/vrs.yaml", "w"))
target = yaml.load(open(root / "data/vrs/vrs.yaml"), Loader=yaml.SafeLoader)


def test_mv_is_passthrough():
    assert processor.class_is_passthrough("MolecularVariation")


def test_se_not_passthrough():
    assert not processor.class_is_passthrough("SequenceExpression")


def test_class_is_subclass():
    assert processor.class_is_subclass("Haplotype", "Variation")
    assert not processor.class_is_subclass("Haplotype", "Location")


def test_yaml_create():
    p = YamlSchemaProcessor(root / "data/gks-common/core-source.yaml")
    p.js_yaml_dump(open(root / "data/gks-common/core.yaml", "w"))
    assert True


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target


def test_merged_create():
    p = YamlSchemaProcessor(root / "data/vrs/vrs-source.yaml")
    p.merge_imported()
    assert True


def test_split_create():
    split_defs_to_js(processor)
    p = YamlSchemaProcessor(root / "data/gnomAD/gnomad-caf-source.yaml")
    split_defs_to_js(p)
    assert True


def test_class_create():
    s2c(processor)
    assert True


@pytest.mark.parametrize(
    "source",
    [
        "data/vrs/vrs-source.yaml",
        "data/gks-common/core-source.yaml",
    ],
)
def test_split_emits_every_class(source):
    """Every non-protected class in a source must produce a JSON file.

    Guards against classes being silently dropped from generation (see #64,
    where abstract classes like Entity/Element were not emitted).
    """
    p = YamlSchemaProcessor(root / source)
    p.json_fp = Path(tempfile.mkdtemp())  # hermetic: do not touch committed fixtures
    split_defs_to_js(p)
    generated = {f.name for f in p.json_fp.iterdir()}
    expected = {c for c in p.processed_classes if not p.class_is_protected(c)}
    assert generated == expected


def test_abstract_root_class_is_generated():
    """Regression guard for #64.

    Abstract classes that carry heritableProperties for inheritance but declare
    no explicit union in the source (e.g. Entity) must still be generated, as a
    oneOf of their concrete descendants.
    """
    p = YamlSchemaProcessor(root / "data/gks-common/core-source.yaml")
    p.json_fp = Path(tempfile.mkdtemp())
    split_defs_to_js(p)
    entity_fp = p.json_fp / "Entity"
    assert entity_fp.exists(), "Entity JSON schema was not generated from core-source.yaml"
    entity = json.load(entity_fp.open())
    assert entity["title"] == "Entity"
    assert "oneOf" in entity, "abstract Entity should concretize to a oneOf of descendants"


def test_docs_create():
    defs = processor.def_fp
    shutil.rmtree(defs, ignore_errors=True)
    os.makedirs(defs)
    y2t(processor)
    assert True


if __name__ == "__main__":
    pytest.main([__file__])
