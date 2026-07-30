"""Tests for generated class, JSON Schema, and RST artifacts."""

from pathlib import Path

from ga4gh.gks.metaschema.scripts.source2classes import main as s2c
from ga4gh.gks.metaschema.scripts.source2splitjs import split_defs_to_js
from ga4gh.gks.metaschema.scripts.y2t import main as y2t
from ga4gh.gks.metaschema.scripts.y2t import resolve_cardinality, resolve_flags, resolve_type
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


def test_split_create_writes_non_protected_json_artifacts(
    schema_root: Path, vrs_processor: YamlSchemaProcessor, tmp_path: Path
) -> None:
    vrs_processor.json_fp = tmp_path / "vrs"
    split_defs_to_js(vrs_processor)

    expected_classes = {
        schema_class
        for schema_class in vrs_processor.for_js[vrs_processor.schema_def_keyword]
        if not vrs_processor.class_is_protected(schema_class)
    }
    generated_classes = {artifact.name for artifact in vrs_processor.json_fp.iterdir()}

    assert generated_classes == expected_classes

    p = YamlSchemaProcessor(schema_root / "gnomAD/gnomad-caf-source.yaml")
    p.json_fp = tmp_path / "gnomAD"
    split_defs_to_js(p)
    assert {artifact.name for artifact in p.json_fp.iterdir()} == {"GnomadCAF"}


def test_split_protected_defs_match_expected_output(schema_root: Path, expected_root: Path, tmp_path: Path) -> None:
    p = YamlSchemaProcessor(schema_root / "gnomAD/gnomad-caf-source.yaml")
    p.json_fp = tmp_path

    split_defs_to_js(p)
    generated = (tmp_path / "GnomadCAF").read_text()
    expected = (expected_root / "source2splitjs/GnomadCAF").read_text()

    assert generated == expected


def test_class_create(vrs_processor: YamlSchemaProcessor) -> None:
    s2c(vrs_processor)


def test_docs_create_matches_expected_rst(schema_root: Path, expected_root: Path, tmp_path: Path) -> None:
    p = YamlSchemaProcessor(schema_root / "vrs/vrs-source.yaml")
    p.def_fp = tmp_path

    y2t(p)

    generated_rst_classes = {artifact.stem for artifact in tmp_path.glob("*.rst")}
    assert generated_rst_classes == set(p.defs)

    # Expected generated output lives outside the source fixture tree so this
    # test catches output changes without relying on broad generated artifacts.
    expected = (expected_root / "y2t/Haplotype.rst").read_text(encoding="utf-8")
    generated = (tmp_path / "Haplotype.rst").read_text(encoding="utf-8")
    assert generated == expected


def test_y2t_resolves_property_type_variants() -> None:
    assert resolve_type({"$ref": "#/$defs/Variation"}) == ":ref:`Variation`"
    assert resolve_type({"type": "array", "items": {"$ref": "#/$defs/Allele"}}) == ":ref:`Allele`"
    assert (
        resolve_type(
            {
                "oneOf": [{"$ref": "#/$defs/Allele"}, {"type": "string"}],
                "deprecated": [{"type": "string"}],
            }
        )
        == ":ref:`Allele` | string (deprecated)"
    )
    assert resolve_type({}) == "_Not Specified_"


def test_y2t_resolves_cardinality_and_flags() -> None:
    class_definition = {"required": ["id"], "heritableRequired": ["label"]}

    assert resolve_cardinality("id", {"type": "string"}, class_definition) == "1..1"
    assert resolve_cardinality("label", {"type": "string"}, class_definition) == "1..1"
    assert resolve_cardinality("name", {"type": "string"}, class_definition) == "0..1"
    assert resolve_cardinality("members", {"type": "array", "minItems": 2, "maxItems": 4}, class_definition) == "2..4"

    flags = resolve_flags({"maturity": "draft", "ordered": False})
    assert "Draft Maturity Level" in flags
    assert "Unordered" in flags
