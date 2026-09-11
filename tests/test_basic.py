import io
import os
import shutil
from pathlib import Path

import pytest
import yaml

from ga4gh.gkm.metaschema.scripts.source2classes import main as s2c
from ga4gh.gkm.metaschema.scripts.y2t import main as y2t
from ga4gh.gkm.metaschema.tools.source_proc import YamlSchemaProcessor

root = Path(__file__).parent

processor = YamlSchemaProcessor(root / "data/vrs/vrs-source.yaml")
# Round-trip the processed schema through YAML in memory (no file artifact).
_yaml_buffer = io.StringIO()
processor.js_yaml_dump(_yaml_buffer)
target = yaml.load(_yaml_buffer.getvalue(), Loader=yaml.SafeLoader)


def test_mv_is_passthrough():
    assert processor.class_is_passthrough("MolecularVariation")


def test_se_not_passthrough():
    assert not processor.class_is_passthrough("SequenceExpression")


def test_class_is_subclass():
    # Allele inherits Variation (directly), so it is a subclass of Variation
    # but not of the unrelated Location hierarchy.
    assert processor.class_is_subclass("Allele", "Variation")
    assert not processor.class_is_subclass("Allele", "Location")


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target


def test_merged_create():
    p = YamlSchemaProcessor(root / "data/vrs/vrs-source.yaml")
    p.merge_imported()
    assert True


def test_class_create():
    s2c(processor)
    assert True


def test_docs_create():
    defs = processor.def_fp
    shutil.rmtree(defs, ignore_errors=True)
    os.makedirs(defs)
    y2t(processor)
    assert True


if __name__ == "__main__":
    pytest.main([__file__])
