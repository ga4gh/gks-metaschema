"""Shared pytest fixtures for metaschema tests."""

from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor


@pytest.fixture(scope="session")
def tests_root() -> Path:
    """Get the tests directory.

    :return: Path to the tests directory.
    """
    return Path(__file__).parent


@pytest.fixture(scope="session")
def schema_root(tests_root: Path) -> Path:
    """Get the shared schema fixture directory.

    :param tests_root: Path to the tests directory.
    :return: Path to ``tests/data/schema``.
    """
    return tests_root / "data/schema"


@pytest.fixture(scope="session")
def schema_case_root(schema_root: Path) -> Path:
    """Get the schema scenario fixture directory.

    :param schema_root: Path to ``tests/data/schema``.
    :return: Path containing named schema test scenarios.
    """
    return schema_root / "cases"


@pytest.fixture(scope="session")
def validation_fixtures(tests_root: Path) -> Path:
    """Get the validation fixture directory.

    :param tests_root: Path to the tests directory.
    :return: Path to ``tests/data/validation``.
    """
    return tests_root / "data/validation"


@pytest.fixture(scope="session")
def schema_case_fixture(schema_case_root: Path) -> Callable[..., Path]:
    """Build paths to product directories in schema scenario fixtures.

    :param schema_case_root: Path containing named schema test scenarios.
    :return: Helper that accepts a scenario name and optional product name.
    """

    def _get_product(name: str, product: str = "example") -> Path:
        """Get a schema scenario product directory.

        :param name: Fixture scenario name.
        :param product: Product directory name under the fixture schema root.
        :return: Fixture product directory path.
        """
        return schema_case_root / name / "schema" / product

    return _get_product


@pytest.fixture(scope="session")
def validation_product_fixture(validation_fixtures: Path) -> Callable[..., Path]:
    """Build paths to product directories in validation fixtures.

    :param validation_fixtures: Path to ``tests/data/validation``.
    :return: Helper that accepts a scenario name and optional product name.
    """

    def _get_product(name: str, product: str = "example") -> Path:
        """Get a validation fixture product directory.

        :param name: Fixture scenario name.
        :param product: Product directory name under the fixture schema root.
        :return: Fixture product directory path.
        """
        return validation_fixtures / name / "schema" / product

    return _get_product


@pytest.fixture(scope="session")
def vrs_processor(schema_root: Path) -> YamlSchemaProcessor:
    """Get a VRS schema processor fixture.

    :param schema_root: Path to ``tests/data/schema``.
    :return: Processor loaded from the VRS source schema.
    """
    return YamlSchemaProcessor(schema_root / "vrs/vrs-source.yaml")


@pytest.fixture(scope="session")
def expected_root(tests_root: Path) -> Path:
    """Get the expected artifact fixture directory.

    :param tests_root: Path to the tests directory.
    :return: Path to ``tests/data/expected``.
    """
    return tests_root / "data/expected"


@pytest.fixture(scope="session")
def vrs_target(expected_root: Path) -> dict:
    """Get the expected processed VRS YAML fixture.

    :param expected_root: Path to ``tests/data/expected``.
    :return: Parsed expected VRS JSON Schema document.
    """
    with (expected_root / "source2yaml/vrs.yaml").open(encoding="utf-8") as stream:
        return yaml.load(stream, Loader=yaml.SafeLoader)
