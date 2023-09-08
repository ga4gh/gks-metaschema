from unittest import TestCase
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


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target


def test_yaml_create():
    p = YamlSchemaProcessor('data/core-source.yaml')
    p.js_yaml_dump(open('data/core.yaml', 'w'))
    assert True


def test_merged_create():
    p = YamlSchemaProcessor('data/vrs-source.yaml')
    p.merge_imported()
    assert True


def test_split_create():
    p = YamlSchemaProcessor('data/vrs-source.yaml')
    p.split_defs_to_js()
    assert True


def test_docs_create():
    defs = Path('data/defs')
    shutil.rmtree(defs, ignore_errors=True)
    os.mkdir(defs)
    p = YamlSchemaProcessor('data/vrs-source.yaml')
    y2t(p, defs)
    assert True
