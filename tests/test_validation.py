"""Tests for schema validation errors."""

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


def test_processor_rejects_missing_class_maturity(
    validation_product_fixture: Callable[[str, str], Path],
) -> None:
    source = validation_product_fixture("missing-maturity") / "example-source.yaml"

    with pytest.raises(ValueError, match="MissingMaturity is missing a maturity value"):
        YamlSchemaProcessor(source)


def test_processor_rejects_array_without_ordered(
    validation_product_fixture: Callable[[str, str], Path],
) -> None:
    source = validation_product_fixture("missing-ordered") / "example-source.yaml"

    with pytest.raises(
        ValueError, match=re.escape("MissingOrdered.values missing ordered attribute")
    ):
        YamlSchemaProcessor(source)


@pytest.mark.parametrize(
    ("fixture_name", "expected_message"),
    [
        (
            "maturity-inheritance",
            "Maturity of Child is greater than parent class Parent",
        ),
        ("bad-extends", "Child.renamed extends unknown inherited property missing"),
        (
            "nonbool-ordered",
            "NonBooleanOrdered.values ordered attribute must be a boolean",
        ),
        (
            "missing-additional-properties",
            '"additionalProperties" expected to be defined in MissingAdditionalProperties.details',
        ),
        ("empty-ga4gh-prefix", "EmptyGa4ghPrefix ga4gh.prefix cannot be empty"),
    ],
)
def test_processor_rejects_invalid_source_schema(
    validation_product_fixture: Callable[[str, str], Path],
    fixture_name: str,
    expected_message: str,
) -> None:
    source = validation_product_fixture(fixture_name) / "example-source.yaml"

    with pytest.raises(ValueError, match=expected_message):
        YamlSchemaProcessor(source)


@pytest.mark.parametrize(
    ("fixture_name", "expected_message"),
    [
        ("duplicate-merge-class", "defines duplicate class\\(es\\): Shared"),
        ("invalid-merge-ref", 'Expected local "\\$ref" definition path'),
    ],
)
def test_merge_imported_definitions_rejects_invalid_imports(
    validation_fixtures: Path, fixture_name: str, expected_message: str
) -> None:
    source = validation_fixtures / fixture_name / "schema/root/root-source.yaml"
    processor = YamlSchemaProcessor(source)

    with pytest.raises(ValueError, match=expected_message):
        processor.merge_imported_definitions()
