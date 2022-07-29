from unittest import TestCase
import yaml
import pytest

from src.ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

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
