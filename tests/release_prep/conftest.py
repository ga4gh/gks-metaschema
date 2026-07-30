"""Shared fixtures for release-preparation tests."""

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

FIXTURE_ROOT = Path(__file__).parents[1] / "data" / "schema" / "cases" / "release-prep"


def copy_release_prep_fixture(tmp_path: Path) -> Path:
    """Copy release-prep fixture data into a temporary directory.

    :param tmp_path: Pytest-provided temporary directory.
    :return: Mutable release-prep fixture copy.
    """
    workdir = tmp_path / "release-prep"
    shutil.copytree(FIXTURE_ROOT, workdir)
    return workdir


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
