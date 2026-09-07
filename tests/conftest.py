"""Shared pytest fixtures for the metaschema test suite.

The YamlSchemaProcessor is expensive to build (it parses YAML and resolves
imports), and it is immutable once constructed, so the processors are built
once per session and reused across tests.
"""

from pathlib import Path

import pytest
from ga4gh.gks.metaschema.tools.source_proc import YamlSchemaProcessor

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def gkm_core_processor() -> YamlSchemaProcessor:
    return YamlSchemaProcessor(DATA / "gkm-core/gkm-core-source.yaml")


@pytest.fixture(scope="session")
def vrs_processor() -> YamlSchemaProcessor:
    return YamlSchemaProcessor(DATA / "vrs/vrs-source.yaml")


@pytest.fixture(scope="session")
def cat_vrs_processor() -> YamlSchemaProcessor:
    return YamlSchemaProcessor(DATA / "catvrs/cat-vrs-source.yaml")


@pytest.fixture(scope="session")
def recipes_processor() -> YamlSchemaProcessor:
    return YamlSchemaProcessor(DATA / "catvrs/recipes-source.yaml")
