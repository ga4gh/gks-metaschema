import yaml
import pytest
import shutil
import os
from pathlib import Path

import ga4gh.gks.metaschema.tools.schema_import

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor
from ga4gh.gks.metaschema.tools.schema_import import construct_url
from ga4gh.gks.metaschema.scripts.y2t import main as y2t
from ga4gh.gks.metaschema.scripts.source2splitjs import split_defs_to_js
from ga4gh.gks.metaschema.scripts.source2classes import main as s2c


root = Path(__file__).parent

processor = YamlSchemaProcessor(root / 'data/vrs/vrs-source.yaml')
processor.js_yaml_dump(open(root /'data/vrs/vrs.yaml', 'w'))
target = yaml.load(open(root /'data/vrs/vrs.yaml'), Loader=yaml.SafeLoader)

def test_mv_is_passthrough():
    assert processor.class_is_passthrough('MolecularVariation')


def test_se_not_passthrough():
    assert not processor.class_is_passthrough('SequenceExpression')


def test_class_is_subclass():
    assert processor.class_is_subclass('Haplotype', 'Variation')
    assert not processor.class_is_subclass('Haplotype', 'Location')


def test_yaml_create():
    p = YamlSchemaProcessor(root /'data/gks-common/core-source.yaml')
    p.js_yaml_dump(open(root /'data/gks-common/core.yaml', 'w'))
    assert True


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target


def test_merged_create():
    p = YamlSchemaProcessor(root /'data/vrs/vrs-source.yaml')
    p.merge_imported()
    assert True


def test_split_create():
    split_defs_to_js(processor)
    p = YamlSchemaProcessor(root /'data/gnomAD/gnomad-caf-source.yaml')
    split_defs_to_js(p)
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

def test_imports():
    spec = {"org":"clingen-data-model",
            "repo":"gks-metaschema",
            "path":"tests/data/vrs/vrs.yaml",
            "sha":"fe2995181d06896f567f81ca4550b3b02830b1e5"}
    target_string = "https://raw.githubusercontent.com/clingen-data-model/gks-metaschema/fe2995181d06896f567f81ca4550b3b02830b1e5/tests/data/vrs/vrs.yaml"
    assert target_string == construct_url(spec)


