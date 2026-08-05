"""Tests for core YAML schema processor behavior."""

from pathlib import Path

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


def test_mv_is_passthrough(vrs_processor: YamlSchemaProcessor) -> None:
    assert vrs_processor.class_is_passthrough("MolecularVariation")


def test_se_not_passthrough(vrs_processor: YamlSchemaProcessor) -> None:
    assert not vrs_processor.class_is_passthrough("SequenceExpression")


def test_class_is_subclass(vrs_processor: YamlSchemaProcessor) -> None:
    assert vrs_processor.class_is_subclass("Haplotype", "Variation")
    assert not vrs_processor.class_is_subclass("Haplotype", "Location")


def test_yaml_create_matches_expected_output(
    schema_root: Path, expected_root: Path, tmp_path: Path
) -> None:
    p = YamlSchemaProcessor(schema_root / "gks-common/core-source.yaml")
    generated_path = tmp_path / "core.yaml"

    with generated_path.open("w", encoding="utf-8") as stream:
        p.js_yaml_dump(stream)

    expected = (expected_root / "source2yaml/core.yaml").read_text(encoding="utf-8")
    generated = generated_path.read_text(encoding="utf-8")
    assert generated == expected


def test_yaml_target_match(
    vrs_processor: YamlSchemaProcessor, vrs_target: dict
) -> None:
    assert vrs_processor.for_js == vrs_target


def test_merged_create(schema_root: Path) -> None:
    p = YamlSchemaProcessor(schema_root / "vrs/vrs-source.yaml")
    p.merge_imported_definitions()
