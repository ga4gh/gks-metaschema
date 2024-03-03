import yaml
import pytest
import shutil
from pathlib import Path
import os

from src.ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor
from src.ga4gh.gks.metaschema.scripts.y2t import main as y2t

target = yaml.load(open('data/vrs.yaml'), Loader=yaml.SafeLoader)

processor = YamlSchemaProcessor('data/vrs-source.yaml')


def test_mv_is_passthrough():
    assert processor.class_is_passthrough('MolecularVariation')


def test_se_not_passthrough():
    assert not processor.class_is_passthrough('SequenceExpression')


def test_class_is_subclass():
    assert processor.class_is_subclass('Haplotype', 'Variation')
    assert not processor.class_is_subclass('Haplotype', 'Location')


def test_yaml_create():
    p = YamlSchemaProcessor('data/imports/core-source.yaml')
    p.js_yaml_dump(open('data/imports/core.yaml', 'w'))
    p = YamlSchemaProcessor('data/vrs-source.yaml')
    p.js_yaml_dump(open('data/vrs.yaml', 'w'))
    assert True


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target


def test_merged_create():
    p = YamlSchemaProcessor('data/vrs-source.yaml')
    p.merge_imported()
    assert True


def test_split_create():
    p = YamlSchemaProcessor('data/vrs-source.yaml')
    p.split_defs_to_js()
    assert True


def test_docs_create():
    p = YamlSchemaProcessor('data/vrs-source.yaml')
    defs = p.def_fp
    shutil.rmtree(defs, ignore_errors=True)
    os.makedirs(defs)
    y2t(p)
    assert True
