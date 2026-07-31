"""Shared fixtures for release-preparation tests."""

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import NoReturn

import pytest

from ga4gh.gks.metaschema.tools.release_prep import schema_versions

FIXTURE_ROOT = Path(__file__).parents[1] / "data" / "schema" / "cases" / "release-prep"


def copy_release_prep_fixture(tmp_path: Path) -> Path:
    """Copy release-prep fixture data into a temporary directory.

    :param tmp_path: Pytest-provided temporary directory.
    :return: Mutable release-prep fixture copy.
    """
    workdir = tmp_path / "release-prep"
    shutil.copytree(FIXTURE_ROOT, workdir)
    return workdir


def run_source_update(product_dir: Path) -> int:
    """Update configured source-schema versions for a test product.

    :param product_dir: Product schema directory containing source YAML files.
    :return: Exit code from the source-version update command.
    """
    return schema_versions.main(["--disallow-versioned-refs", str(product_dir)])


def unexpected_command(command: list[str], cwd: Path) -> NoReturn:
    """Fail a test for an unexpected command invocation.

    :param command: Command received by the test stub.
    :param cwd: Command working directory received by the test stub.
    """
    msg = f"unexpected output command: {command} in {cwd}"
    raise AssertionError(msg)


@pytest.fixture
def release_prep_workdir(tmp_path: Path) -> Callable[[], Path]:
    """Return a factory for a mutable copy of the release-prep fixture.

    :param tmp_path: Pytest-provided temporary directory.
    :return: Callable that creates and returns a fixture copy.
    """

    def create_workdir() -> Path:
        """Copy release-prep fixture data into the test temporary directory."""
        return copy_release_prep_fixture(tmp_path)

    return create_workdir
