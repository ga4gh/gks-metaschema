import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

from ga4gh.gks.metaschema.scripts.source2classes import main as s2c
from ga4gh.gks.metaschema.scripts.source2splitjs import split_defs_to_js
from ga4gh.gks.metaschema.scripts.update_schema_versions import main as update_schema_versions
from ga4gh.gks.metaschema.scripts.y2t import main as y2t
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

root = Path(__file__).parent
schema_root = root / "data/schema"
metaschema_fixtures = root / "data/metaschema"


def metaschema_product_fixture(name: str, product: str = "example") -> Path:
    """Get a metaschema fixture product directory.

    :param name: Fixture scenario name.
    :param product: Product directory name under the fixture schema root.
    :return: Fixture product directory path.
    """
    return metaschema_fixtures / name / "schema" / product


processor = YamlSchemaProcessor(schema_root / "vrs/vrs-source.yaml")
processor.js_yaml_dump(open(schema_root / "vrs/vrs.yaml", "w"))
target = yaml.load(open(schema_root / "vrs/vrs.yaml"), Loader=yaml.SafeLoader)


def test_mv_is_passthrough():
    assert processor.class_is_passthrough("MolecularVariation")


def test_se_not_passthrough():
    assert not processor.class_is_passthrough("SequenceExpression")


def test_class_is_subclass():
    assert processor.class_is_subclass("Haplotype", "Variation")
    assert not processor.class_is_subclass("Haplotype", "Location")


def test_yaml_create():
    p = YamlSchemaProcessor(schema_root / "gks-common/core-source.yaml")
    p.js_yaml_dump(open(schema_root / "gks-common/core.yaml", "w"))
    assert True


def test_yaml_target_match():
    d2 = processor.for_js
    assert d2 == target


def test_merged_create():
    p = YamlSchemaProcessor(schema_root / "vrs/vrs-source.yaml")
    p.merge_imported()
    assert True


def test_split_create():
    split_defs_to_js(processor)
    p = YamlSchemaProcessor(schema_root / "gnomAD/gnomad-caf-source.yaml")
    split_defs_to_js(p)
    assert True


def test_split_protected_defs_order_is_stable(tmp_path):
    p = YamlSchemaProcessor(schema_root / "gnomAD/gnomad-caf-source.yaml")
    p.json_fp = tmp_path

    split_defs_to_js(p)
    first = (tmp_path / "GnomadCAF").read_text()
    split_defs_to_js(p)
    second = (tmp_path / "GnomadCAF").read_text()

    assert first == second
    assert first.index('"GnomadCafProperties"') < first.index('"GrpMaxFAF95"')


def test_class_create():
    s2c(processor)
    assert True


def test_docs_create():
    defs = processor.def_fp
    shutil.rmtree(defs, ignore_errors=True)
    os.makedirs(defs)
    y2t(processor)
    assert True


def test_update_schema_versions_updates_configured_refs(tmp_path):
    shutil.copytree(metaschema_fixtures / "update", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/profile-source.yaml"

    assert update_schema_versions([str(source)]) == 0

    updated = source.read_text()
    assert "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/va-spec-source.yaml" in updated
    assert '"/ga4gh/schema/va-spec/1.1.0/base/json/VariantPrognosticProposition"' in updated
    assert '"/ga4gh/schema/unmanaged/9.9.9/json/Thing"' in updated
    assert "namespaces:" not in updated


def test_update_schema_versions_discovers_config_from_path(tmp_path):
    shutil.copytree(metaschema_fixtures / "update", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/profile-source.yaml"

    assert update_schema_versions([str(tmp_path / "schema")]) == 0

    assert "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/va-spec-source.yaml" in source.read_text()


def test_update_schema_versions_uses_product_config_under_schema_root(tmp_path):
    shutil.copytree(metaschema_fixtures / "schema-root", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/va-spec/base/domain-entities-source.yaml"

    assert update_schema_versions([str(tmp_path / "schema")]) == 0

    assert "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/domain-entities-source.yaml" in source.read_text()


def test_update_schema_versions_check_reports_source_local_config_keys(tmp_path, capsys):
    shutil.copytree(metaschema_fixtures / "update", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/profile-source.yaml"

    assert update_schema_versions(["--check", str(source)]) == 1

    assert "namespaces is managed by metaschema.yaml" in capsys.readouterr().err


def test_update_schema_versions_noops_without_default_config(tmp_path):
    shutil.copytree(metaschema_fixtures / "no-config", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/example-source.yaml"

    with pytest.raises(ValueError, match="No metaschema.yaml config found for"):
        update_schema_versions([str(source)])


def test_update_schema_versions_check_reports_stale_refs(tmp_path, capsys):
    shutil.copytree(metaschema_fixtures / "check", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/example-source.yaml"

    assert update_schema_versions(["--check", str(source)]) == 1

    assert "va-spec is 1.0.1; expected 1.1.0" in capsys.readouterr().err
    assert "1.0.1" in source.read_text()


def test_update_schema_versions_check_rejects_version_template(capsys):
    source = metaschema_product_fixture("check") / "current-template-source.yaml"

    assert update_schema_versions(["--check", str(source)]) == 1

    assert "va-spec is {version}; expected 1.1.0" in capsys.readouterr().err


def test_update_schema_versions_can_disallow_hardcoded_refs(capsys):
    source = metaschema_product_fixture("hardcoded-ref") / "profile-source.yaml"
    assert update_schema_versions(["--disallow-versioned-refs", str(source)]) == 1
    assert "hard-coded $ref" in capsys.readouterr().err


def test_update_schema_versions_ignores_commented_hardcoded_refs(tmp_path, capsys):
    shutil.copytree(metaschema_fixtures / "hardcoded-ref", tmp_path, dirs_exist_ok=True)
    source = tmp_path / "schema/example/profile-source.yaml"
    source.write_text(
        '\n$id: "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/profile-source.yaml"\n'
        "$defs:\n"
        "  Example:\n"
        '    # $ref: "/ga4gh/schema/va-spec/1.1.0/base/json/CommentedOutProposition"\n',
        encoding="utf-8",
    )

    assert update_schema_versions(["--disallow-versioned-refs", str(source)]) == 0
    assert "hard-coded $ref" not in capsys.readouterr().err


def test_schema_makefiles_disallow_versioned_refs():
    makefiles = [
        schema_root / "vrs/Makefile",
        schema_root / "catvrs/Makefile",
        schema_root / "gnomAD/Makefile",
        schema_root / "gks-common/Makefile",
        schema_root / "va-spec/core-im/Makefile",
        schema_root / "va-spec/profiles/pathogenicity/Makefile",
        schema_root / "va-spec/profiles/caf/Makefile",
        schema_root / "va-spec/profiles/oncogenicity/Makefile",
        schema_root / "va-spec/profiles/t-resp/Makefile",
    ]

    for makefile in makefiles:
        assert "source2updated --disallow-versioned-refs ." in makefile.read_text()


def test_metaschema_config_populates_imports_and_namespaces():
    source = metaschema_product_fixture("processor") / "example-source.yaml"

    p = YamlSchemaProcessor(source)

    assert p.id == "https://w3id.org/ga4gh/schema/example/1.0.0/example-source.yaml"
    assert "vrs" in p.imports
    assert p.imports["vrs"].imports == {}
    assert p.imports["vrs"].get_metaschema_config_fp() == metaschema_fixtures / "processor/schema/vrs/metaschema.yaml"
    assert p.namespaces["vrs"] == "/ga4gh/schema/vrs/2.2.0/json/"
    assert p.for_js["$defs"]["Example"]["properties"]["variation"]["$ref"] == "/ga4gh/schema/vrs/2.2.0/json/Variation"


def test_downstream_metaschema_only_needs_direct_imports():
    source = metaschema_product_fixture("direct-imports", "downstream") / "downstream-source.yaml"

    p = YamlSchemaProcessor(source)

    assert set(p.imports) == {"mid"}
    assert "upstream" not in p.namespaces
    assert set(p.imports["mid"].imports) == {"upstream"}
    assert p.imports["mid"].namespaces["upstream"] == "/ga4gh/schema/upstream/3.0.0/json/"
    assert (
        p.imports["mid"].for_js["$defs"]["MidClass"]["properties"]["upstream"]["$ref"]
        == "/ga4gh/schema/upstream/3.0.0/json/UpstreamClass"
    )


def test_nested_source_uses_top_level_metaschema_config():
    source = metaschema_fixtures / "schema-root/schema/va-spec/base/current-domain-entities-source.yaml"
    p = YamlSchemaProcessor(source)

    assert p.get_metaschema_config_fp() == metaschema_fixtures / "schema-root/schema/va-spec/metaschema.yaml"
    assert p.id == "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/current-domain-entities-source.yaml"


def test_nested_metaschema_config_raises_error():
    source = metaschema_fixtures / "nested-manifest/schema/example/nested/example-source.yaml"

    with pytest.raises(ValueError, match="Nested metaschema.yaml files are not supported"):
        YamlSchemaProcessor(source)


def test_metaschema_config_uses_concrete_versions_in_js_outputs(tmp_path):
    source = metaschema_product_fixture("processor") / "example-source.yaml"
    p = YamlSchemaProcessor(source)

    assert "{version}" not in json.dumps(p.for_js)
    assert "$refCurie" not in json.dumps(p.for_js)

    p.json_fp = tmp_path
    split_defs_to_js(p)

    generated = (tmp_path / "Example").read_text()
    assert "{version}" not in generated
    assert "$refCurie" not in generated
    assert "https://w3id.org/ga4gh/schema/example/1.0.0/json/Example" in generated


def test_split_defs_converts_ref_curies_before_writing_json(tmp_path):
    source = metaschema_product_fixture("processor") / "example-source.yaml"
    p = YamlSchemaProcessor(source)
    p.for_js["$defs"]["Example"]["properties"]["variation"] = {"$refCurie": "vrs:Variation"}

    p.json_fp = tmp_path
    split_defs_to_js(p)

    generated = (tmp_path / "Example").read_text()
    assert "$refCurie" not in generated
    assert '"/ga4gh/schema/vrs/2.2.0/json/Variation"' in generated


def test_split_defs_converts_ref_curies_from_configured_namespaces(tmp_path):
    source = metaschema_product_fixture("processor") / "example-source.yaml"
    p = YamlSchemaProcessor(source)
    p.namespaces["gks.core"] = "/ga4gh/schema/gks-core/1.2.0/json/"
    p.for_js["$defs"]["Example"]["properties"]["coding"] = {
        "allOf": [
            {"$refCurie": "gks.core:Coding"},
            {"properties": {"code": {"enum": ["A", "B"]}}},
        ]
    }

    p.json_fp = tmp_path
    split_defs_to_js(p)

    generated = (tmp_path / "Example").read_text()
    assert "$refCurie" not in generated
    assert '"/ga4gh/schema/gks-core/1.2.0/json/Coding"' in generated


def test_split_refs_load_imports_from_external_ref_artifact_stem(tmp_path):
    source = metaschema_fixtures / "external-ref/schema/catvrs/categorical-source.yaml"
    p = YamlSchemaProcessor(source)

    assert "model" in p.imports

    p.json_fp = tmp_path
    split_defs_to_js(p)

    generated = (tmp_path / "CategoricalVariation").read_text()
    assert "/ga4gh/schema/catvrs/1.0.0/model/json/CategoricalVariant" in generated


def test_metaschema_config_rejects_version_template_in_source_id():
    source = metaschema_product_fixture("stale-id") / "example-source.yaml"

    with pytest.raises(ValueError, match=r"example \$id version is \{version\}; expected 1.0.0"):
        YamlSchemaProcessor(source)


def test_metaschema_config_rejects_unknown_keys():
    source = metaschema_product_fixture("unknown-key") / "example-source.yaml"

    with pytest.warns(
        UserWarning,
        match="Ignoring unsupported metaschema config keys: unexpected. Allowed keys are: imports, namespaces, versions",
    ):
        YamlSchemaProcessor(source)


def test_metaschema_config_ignores_source_imports_and_namespaces():
    source = metaschema_product_fixture("source-local") / "example-source.yaml"
    imported = metaschema_product_fixture("source-local") / "config-vrs-source.yaml"

    with pytest.warns(UserWarning, match="ignoring source-local"):
        p = YamlSchemaProcessor(source)

    assert p.raw_schema["imports"]["vrs"] == str(imported)
    assert p.imports["vrs"].imports == {}
    assert p.namespaces["vrs"] == "/ga4gh/schema/vrs/2.2.0/json/"


def test_metaschema_config_allows_matching_concrete_namespace_version():
    source = metaschema_product_fixture("concrete-namespace") / "example-source.yaml"

    p = YamlSchemaProcessor(source)

    assert p.namespaces["vrs"] == "/ga4gh/schema/vrs/2.2.0/json/"


def test_metaschema_config_rejects_stale_concrete_namespace_version():
    source = metaschema_product_fixture("stale-namespace") / "example-source.yaml"

    with pytest.raises(ValueError, match="namespace vrs vrs version is 2.0.0; expected 2.2.0"):
        YamlSchemaProcessor(source)


def test_metaschema_config_rejects_missing_namespace_version():
    source = metaschema_product_fixture("missing-namespace-version") / "example-source.yaml"

    with pytest.raises(ValueError, match=r"namespace vrs uses \{version\} but no version is configured for vrs"):
        YamlSchemaProcessor(source)


if __name__ == "__main__":
    pytest.main([__file__])
