from unittest import TestCase
import yaml
import pytest

from src.ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

target = yaml.load(open('data/vrs.yaml'), Loader=yaml.SafeLoader)

processor = YamlSchemaProcessor('data/vrs-source.yaml')


def test_mv_is_passthrough():
    assert processor.class_is_passthrough('MolecularVariation')


def test_loc_not_passthrough():
    assert not processor.class_is_passthrough('Location')


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target
