import json
import yaml

from src.ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

source = yaml.load(open('data/vrs-source.yaml'), Loader=yaml.SafeLoader)
target = yaml.load(open('data/vrs.yaml'), Loader=yaml.SafeLoader)

processor = YamlSchemaProcessor(source)


def test_yaml_target_match():
    assert processor.for_js == target
