"""Tests for release-prep Git submodule behavior."""

import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import copy_release_prep_fixture

from ga4gh.gks.metaschema.tools.release_prep import cli as release_prep
from ga4gh.gks.metaschema.tools.release_prep.cli import (
    prepare_release,
)
from ga4gh.gks.metaschema.tools.release_prep.git import (
    SubmoduleUpdate,
    select_highest_semantic_tag,
)


def _clean_output(command: list[str], cwd: Path) -> str:
    """Return clean git status output for tests that use explicit tags."""
    if command == ["git", "status", "--porcelain"]:
        return ""
    if command == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
        return "origin/main"
    if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
        return "0\t0"

    raise AssertionError(f"unexpected output command: {command} in {cwd}")


def _run_fixture_make_all(command: list[str], cwd: Path, product_dir: Path) -> None:
    """Model the source update performed by the product ``make all`` target.

    :param command: Command passed to the fake runner.
    :param cwd: Command working directory.
    :param product_dir: Product schema directory to update.
    """
    if command != ["make", "all"]:
        return

    assert cwd == product_dir.parent.resolve()
    exit_code = release_prep._run_source_update(product_dir.resolve(), check=False)
    assert exit_code == 0


def test_select_highest_semantic_tag_uses_packaging_version_order() -> None:
    """Select the highest semantic-version tag while preserving the git tag text."""
    tag = select_highest_semantic_tag(
        ["not-a-version", "v2.2.0-ballot.2026-07.1", "v2.1.9", "v2.2.0-ballot.2026-07.2"],
        SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot"),
        "origin/2.2.0-ballot",
    )

    assert tag == "v2.2.0-ballot.2026-07.2"


def test_select_highest_semantic_tag_supports_ballot_versions() -> None:
    """Support GKS ballot tag versions that are not directly PEP 440-compatible."""
    tag = select_highest_semantic_tag(
        ["v1.2.0-ballot.2026-07.1", "v1.2.0-ballot.2026-07.2"],
        SubmoduleUpdate(identifier="cat-vrs", branch="1.2.0-ballot.2026-07"),
        "origin/1.2.0-ballot.2026-07",
    )

    assert tag == "v1.2.0-ballot.2026-07.2"


def test_prepare_release_initializes_missing_submodule(tmp_path: Path) -> None:
    """Initialize a configured submodule checkout when it is missing locally."""
    workdir = copy_release_prep_fixture(tmp_path)
    submodule_dir = workdir / "schema" / "submodules" / "vrs"
    shutil.rmtree(submodule_dir)
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record commands and create the submodule directory on init."""
        commands.append((command, cwd))
        if command == ["git", "submodule", "update", "--init", "--", "schema/submodules/vrs"]:
            submodule_dir.mkdir(parents=True)
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")],
        runner=runner,
        output_runner=_clean_output,
    )

    assert commands[:5] == [
        (["git", "submodule", "update", "--init", "--", "schema/submodules/vrs"], workdir.resolve()),
        (["git", "fetch", "--all", "--tags"], submodule_dir),
        (["git", "rev-parse", "--verify", "origin/2.2.0-ballot^{commit}"], submodule_dir),
        (["git", "rev-parse", "--verify", "v2.2.0^{commit}"], submodule_dir),
        (["git", "submodule", "update", "--remote", "--init", "--", "schema/submodules/vrs"], workdir.resolve()),
    ]


def test_prepare_release_matches_submodule_identifier_to_gitmodules_path_basename(tmp_path: Path) -> None:
    """Allow CLI identifiers like gks-core to match path submodules/gks-core."""
    workdir = copy_release_prep_fixture(tmp_path)
    gitmodules_fp = workdir / ".gitmodules"
    gitmodules_fp.write_text(
        """[submodule "schema/submodules/gks-core"]\n\tpath = schema/submodules/gks-core\n\turl = https://github.com/ga4gh/gks-core.git\n\tbranch = 1.1.0\n""",
        encoding="utf-8",
    )
    gks_core_dir = workdir / "schema" / "submodules" / "gks-core"
    gks_core_dir.mkdir(parents=True)
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record release commands instead of running git or make."""
        commands.append((command, cwd))
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[SubmoduleUpdate(identifier="gks-core", branch="1.2.0-ballot.2026-07", tag="v1.2.0")],
        runner=runner,
        output_runner=_clean_output,
    )

    assert "\tbranch = 1.2.0-ballot.2026-07" in gitmodules_fp.read_text(encoding="utf-8")
    assert commands[0] == (["git", "fetch", "--all", "--tags"], gks_core_dir.resolve())
    assert commands[3] == (
        ["git", "submodule", "update", "--remote", "--init", "--", "schema/submodules/gks-core"],
        workdir.resolve(),
    )


def test_prepare_release_rejects_unknown_submodule_identifier(tmp_path: Path) -> None:
    """Reject submodule identifiers that are not configured in .gitmodules."""
    workdir = copy_release_prep_fixture(tmp_path)

    with pytest.raises(ValueError, match="Could not find a .gitmodules entry for submodule missing"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="missing", branch="1.0.0-ballot")],
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_multiple_submodule_updates(tmp_path: Path) -> None:
    """Reject release prep that tries to update more than one upstream product."""
    workdir = copy_release_prep_fixture(tmp_path)

    with pytest.raises(ValueError, match="one immediate upstream submodule"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[
                SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot"),
                SubmoduleUpdate(identifier="cat-vrs", branch="1.2.0-ballot"),
            ],
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_submodule_directory(tmp_path: Path) -> None:
    """Reject release prep when the configured submodule directory is absent."""
    workdir = copy_release_prep_fixture(tmp_path)
    shutil.rmtree(workdir / "schema" / "submodules" / "vrs")

    def runner(command: list[str], cwd: Path) -> None:
        """Do not create the missing submodule directory."""

    with pytest.raises(ValueError, match="does not exist after update"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            runner=runner,
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_submodule_branch(tmp_path: Path) -> None:
    """Reject release prep when the requested submodule branch is not available."""
    workdir = copy_release_prep_fixture(tmp_path)

    def runner(command: list[str], cwd: Path) -> None:
        """Fail the git branch validation command."""
        if command == ["git", "rev-parse", "--verify", "origin/9.9.9-ballot^{commit}"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=command)

    with pytest.raises(ValueError, match="Could not find git branch origin/9.9.9-ballot"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="9.9.9-ballot")],
            runner=runner,
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_submodule_tag(tmp_path: Path) -> None:
    """Reject release prep when the requested submodule tag is not available."""
    workdir = copy_release_prep_fixture(tmp_path)

    def runner(command: list[str], cwd: Path) -> None:
        """Fail the git tag validation command."""
        if command == ["git", "rev-parse", "--verify", "v9.9.9^{commit}"]:
            raise subprocess.CalledProcessError(returncode=1, cmd=command)

    with pytest.raises(ValueError, match="Could not find git tag v9.9.9"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v9.9.9")],
            runner=runner,
            output_runner=_clean_output,
        )


def test_prepare_release_rejects_missing_latest_submodule_tag(tmp_path: Path) -> None:
    """Reject release prep when no latest reachable tag can be discovered."""
    workdir = copy_release_prep_fixture(tmp_path)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git or make commands for this test."""

    def output_runner(command: list[str], cwd: Path) -> str:
        """Fail latest tag discovery."""
        if command == ["git", "status", "--porcelain"]:
            return ""
        raise subprocess.CalledProcessError(returncode=1, cmd=command)

    with pytest.raises(ValueError, match="Could not find a reachable git tag"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            runner=runner,
            output_runner=output_runner,
        )


def test_prepare_release_rejects_missing_gitmodules_entry(tmp_path: Path) -> None:
    """Reject release prep when no .gitmodules entry matches the submodule."""
    workdir = copy_release_prep_fixture(tmp_path)
    (workdir / ".gitmodules").write_text(
        """[submodule "schema/submodules/other"]\n\tpath = schema/submodules/other\n\turl = https://example.org/other.git\n""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Could not find a .gitmodules entry"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            output_runner=_clean_output,
        )


def test_prepare_release_adds_missing_gitmodules_branch(tmp_path: Path) -> None:
    """Add a branch key when the matching .gitmodules entry does not have one."""
    workdir = copy_release_prep_fixture(tmp_path)
    gitmodules_fp = workdir / ".gitmodules"
    gitmodules_fp.write_text(
        """[submodule "schema/submodules/vrs"]\n\tpath = schema/submodules/vrs\n\turl = https://github.com/ga4gh/vrs.git\n""",
        encoding="utf-8",
    )

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git or make commands for this test."""
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")],
        runner=runner,
        output_runner=_clean_output,
    )

    assert "\tbranch = 2.2.0-ballot" in gitmodules_fp.read_text(encoding="utf-8")
