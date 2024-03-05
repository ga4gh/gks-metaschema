import yaml
import pytest
import shutil
import os

from src.ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor
from src.ga4gh.gks.metaschema.scripts.y2t import main as y2t
from src.ga4gh.gks.metaschema.scripts.source2splitjs import split_defs_to_js
from src.ga4gh.gks.metaschema.scripts.source2classes import main as s2c

processor = YamlSchemaProcessor('data/vrs/vrs-source.yaml')
processor.js_yaml_dump(open('data/vrs/vrs.yaml', 'w'))
target = yaml.load(open('data/vrs/vrs.yaml'), Loader=yaml.SafeLoader)

def test_mv_is_passthrough():
    assert processor.class_is_passthrough('MolecularVariation')


def test_se_not_passthrough():
    assert not processor.class_is_passthrough('SequenceExpression')


def test_class_is_subclass():
    assert processor.class_is_subclass('Haplotype', 'Variation')
    assert not processor.class_is_subclass('Haplotype', 'Location')


def test_yaml_create():
    p = YamlSchemaProcessor('data/gks-common/core-source.yaml')
    p.js_yaml_dump(open('data/gks-common/core.yaml', 'w'))
    assert True


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target


def test_merged_create():
    p = YamlSchemaProcessor('data/vrs/vrs-source.yaml')
    p.merge_imported()
    assert True


def test_split_create():
    split_defs_to_js(processor)
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
