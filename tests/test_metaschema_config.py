"""Tests for loading and applying product-level metaschema configuration."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from ga4gh.gks.metaschema.scripts.source2splitjs import split_defs_to_js
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


def test_metaschema_config_populates_imports_and_namespaces(
    schema_case_fixture: Callable[..., Path], schema_case_root: Path
) -> None:
    source = schema_case_fixture("processor") / "example-source.yaml"

    p = YamlSchemaProcessor(source)

    assert p.id == "https://w3id.org/ga4gh/schema/example/1.0.0/example-source.yaml"
    assert "vrs" in p.imports
    assert p.imports["vrs"].imports == {}
    assert p.imports["vrs"].get_metaschema_config_fp() == schema_case_root / "processor/schema/vrs/metaschema.yaml"
    assert p.namespaces["vrs"] == "/ga4gh/schema/vrs/2.2.0/json/"
    assert p.for_js["$defs"]["Example"]["properties"]["variation"]["$ref"] == "/ga4gh/schema/vrs/2.2.0/json/Variation"


def test_downstream_metaschema_only_needs_direct_imports(
    schema_case_fixture: Callable[..., Path],
) -> None:
    source = schema_case_fixture("direct-imports", "downstream") / "downstream-source.yaml"

    p = YamlSchemaProcessor(source)

    assert set(p.imports) == {"mid"}
    assert "upstream" not in p.namespaces
    assert set(p.imports["mid"].imports) == {"upstream"}
    assert p.imports["mid"].namespaces["upstream"] == "/ga4gh/schema/upstream/3.0.0/json/"
    assert (
        p.imports["mid"].for_js["$defs"]["MidClass"]["properties"]["upstream"]["$ref"]
        == "/ga4gh/schema/upstream/3.0.0/json/UpstreamClass"
    )


def test_nested_source_uses_top_level_metaschema_config(schema_case_root: Path) -> None:
    source = schema_case_root / "schema-root/schema/va-spec/base/current-domain-entities-source.yaml"
    p = YamlSchemaProcessor(source)

    assert p.get_metaschema_config_fp() == schema_case_root / "schema-root/schema/va-spec/metaschema.yaml"
    assert p.id == "https://w3id.org/ga4gh/schema/va-spec/1.1.0/base/current-domain-entities-source.yaml"


def test_nested_metaschema_config_raises_error(schema_case_root: Path) -> None:
    source = schema_case_root / "nested-manifest/schema/example/nested/example-source.yaml"

    with pytest.raises(ValueError, match="Nested metaschema.yaml files are not supported"):
        YamlSchemaProcessor(source)


def test_metaschema_config_uses_concrete_versions_in_js_outputs(
    schema_case_fixture: Callable[..., Path], tmp_path: Path
) -> None:
    source = schema_case_fixture("processor") / "example-source.yaml"
    p = YamlSchemaProcessor(source)

    assert "{version}" not in json.dumps(p.for_js)
    assert "$refCurie" not in json.dumps(p.for_js)

    p.json_fp = tmp_path
    split_defs_to_js(p)

    generated = (tmp_path / "Example").read_text()
    assert "{version}" not in generated
    assert "$refCurie" not in generated
    assert "https://w3id.org/ga4gh/schema/example/1.0.0/json/Example" in generated


def test_split_defs_converts_ref_curies_before_writing_json(
    schema_case_fixture: Callable[..., Path], tmp_path: Path
) -> None:
    source = schema_case_fixture("processor") / "example-source.yaml"
    p = YamlSchemaProcessor(source)
    p.for_js["$defs"]["Example"]["properties"]["variation"] = {"$refCurie": "vrs:Variation"}

    p.json_fp = tmp_path
    split_defs_to_js(p)

    generated = (tmp_path / "Example").read_text()
    assert "$refCurie" not in generated
    assert '"/ga4gh/schema/vrs/2.2.0/json/Variation"' in generated


def test_split_defs_converts_ref_curies_from_configured_namespaces(
    schema_case_fixture: Callable[..., Path], tmp_path: Path
) -> None:
    source = schema_case_fixture("processor") / "example-source.yaml"
    p = YamlSchemaProcessor(source)
    # This alias is intentionally namespace-only: MSP can render the external
    # output ref without loading the upstream product as an import.
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


def test_split_refs_load_imports_from_external_ref_artifact_stem(schema_case_root: Path, tmp_path: Path) -> None:
    source = schema_case_root / "external-ref/schema/catvrs/categorical-source.yaml"
    p = YamlSchemaProcessor(source)

    assert "model" in p.imports

    p.json_fp = tmp_path
    split_defs_to_js(p)

    generated = (tmp_path / "CategoricalVariation").read_text()
    assert "/ga4gh/schema/catvrs/1.0.0/model/json/CategoricalVariant" in generated


def test_metaschema_config_rejects_version_template_in_source_id(
    schema_case_fixture: Callable[..., Path],
) -> None:
    source = schema_case_fixture("stale-id") / "example-source.yaml"

    with pytest.raises(ValueError, match=r"example \$id version is \{version\}; expected 1.0.0"):
        YamlSchemaProcessor(source)


def test_metaschema_config_rejects_unknown_keys(schema_case_fixture: Callable[..., Path]) -> None:
    source = schema_case_fixture("unknown-key") / "example-source.yaml"

    with pytest.warns(
        UserWarning,
        match="Ignoring unsupported metaschema config keys: unexpected. Allowed keys are: imports, namespaces, versions",
    ):
        YamlSchemaProcessor(source)


def test_metaschema_config_ignores_source_imports_and_namespaces(
    schema_case_fixture: Callable[..., Path],
) -> None:
    source = schema_case_fixture("source-local") / "example-source.yaml"
    imported = schema_case_fixture("source-local") / "config-vrs-source.yaml"

    with pytest.warns(UserWarning, match="ignoring source-local"):
        p = YamlSchemaProcessor(source)

    assert p.raw_schema["imports"]["vrs"] == str(imported)
    assert p.imports["vrs"].imports == {}
    assert p.namespaces["vrs"] == "/ga4gh/schema/vrs/2.2.0/json/"


def test_metaschema_config_allows_matching_concrete_namespace_version(
    schema_case_fixture: Callable[..., Path],
) -> None:
    source = schema_case_fixture("concrete-namespace") / "example-source.yaml"

    p = YamlSchemaProcessor(source)

    assert p.namespaces["vrs"] == "/ga4gh/schema/vrs/2.2.0/json/"


def test_metaschema_config_rejects_stale_concrete_namespace_version(
    schema_case_fixture: Callable[..., Path],
) -> None:
    source = schema_case_fixture("stale-namespace") / "example-source.yaml"

    with pytest.raises(ValueError, match="namespace vrs vrs version is 2.0.0; expected 2.2.0"):
        YamlSchemaProcessor(source)


def test_metaschema_config_rejects_missing_namespace_version(
    schema_case_fixture: Callable[..., Path],
) -> None:
    source = schema_case_fixture("missing-namespace-version") / "example-source.yaml"

    with pytest.raises(ValueError, match=r"namespace vrs uses \{version\} but no version is configured for vrs"):
        YamlSchemaProcessor(source)
