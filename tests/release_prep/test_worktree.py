"""Tests for release-prep worktree status handling."""

from pathlib import Path

import pytest
from conftest import copy_release_prep_fixture, run_source_update, unexpected_command

from ga4gh.gks.metaschema.tools.release_prep.cli import (
    prepare_release,
)
from ga4gh.gks.metaschema.tools.release_prep.git import (
    SubmoduleUpdate,
)


def _clean_output(command: list[str], cwd: Path) -> str:
    """Return clean git status output for tests that use explicit tags."""
    if command == ["git", "status", "--porcelain"]:
        return ""
    if command == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
        return "origin/main"
    if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
        return "0\t0"

    return unexpected_command(command, cwd)


def _run_fixture_make_all(command: list[str], cwd: Path, product_dir: Path) -> None:
    """Model the source update performed by the product ``make all`` target.

    :param command: Command passed to the fake runner.
    :param cwd: Command working directory.
    :param product_dir: Product schema directory to update.
    """
    if command != ["make", "all"]:
        return

    assert cwd == product_dir.parent.resolve()
    exit_code = run_source_update(product_dir.resolve())
    assert exit_code == 0


def test_prepare_release_can_reject_dirty_product_repo(tmp_path: Path) -> None:
    """Reject a dirty product repo when strict dirty-worktree mode is enabled."""
    workdir = copy_release_prep_fixture(tmp_path)

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the product repo."""
        if command == ["git", "status", "--porcelain"]:
            return " M schema/example/metaschema.yaml"

        return unexpected_command(command, cwd)

    with pytest.raises(ValueError, match="Product example has uncommitted changes"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            output_runner=output_runner,
            fail_on_dirty=True,
        )


def test_prepare_release_can_reject_dirty_submodule(tmp_path: Path) -> None:
    """Reject a dirty upstream submodule when strict dirty-worktree mode is enabled."""
    workdir = copy_release_prep_fixture(tmp_path)
    submodule_dir = (workdir / "schema" / "submodules" / "vrs").resolve()

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the submodule only."""
        if command == ["git", "status", "--porcelain"] and cwd == submodule_dir:
            return " M schema/vrs/vrs-source.yaml"
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t0"

        return unexpected_command(command, cwd)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git commands for this test."""

    with pytest.raises(ValueError, match="Submodule vrs has uncommitted changes"):
        prepare_release(
            product="example",
            version="1.1.0",
            repo_dir=workdir,
            submodules=[SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot")],
            runner=runner,
            output_runner=output_runner,
            fail_on_dirty=True,
        )


def test_prepare_release_warns_for_dirty_product_repo_by_default(
    tmp_path: Path,
) -> None:
    """Warn and continue when the product repo is dirty by default."""
    repo_dir = tmp_path / "gks-core"
    product_dir = repo_dir / "schema" / "gks-core"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text(
        "versions:\n  gks-core: 3.0.0\n", encoding="utf-8"
    )
    messages: list[str] = []

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the product repo."""
        if command == ["git", "status", "--porcelain"]:
            return " M schema/gks-core/metaschema.yaml"

        return unexpected_command(command, cwd)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run make for this test."""

    prepare_release(
        product="gks-core",
        version="3.0.0",
        repo_dir=repo_dir,
        submodules=None,
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert (
        "Warning: Product gks-core has uncommitted changes. Review the final diff carefully."
        in messages
    )


def test_prepare_release_warns_for_dirty_submodule_by_default(tmp_path: Path) -> None:
    """Warn and continue when the upstream submodule is dirty by default."""
    workdir = copy_release_prep_fixture(tmp_path)
    submodule_dir = (workdir / "schema" / "submodules" / "vrs").resolve()
    messages: list[str] = []

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return dirty status for the submodule only."""
        if command == ["git", "status", "--porcelain"] and cwd == submodule_dir:
            return " M schema/vrs/vrs-source.yaml"
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t0"

        return unexpected_command(command, cwd)

    def runner(command: list[str], cwd: Path) -> None:
        """Model make all without running git or make commands."""
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
        ],
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert (
        "Warning: Submodule vrs has uncommitted changes. Review the final diff carefully."
        in messages
    )


def test_prepare_release_warns_when_product_branch_is_behind(tmp_path: Path) -> None:
    """Warn, without failing, when the product branch is behind its upstream."""
    workdir = copy_release_prep_fixture(tmp_path)
    messages: list[str] = []

    def output_runner(command: list[str], cwd: Path) -> str:
        """Return a clean but behind product branch state."""
        if command == ["git", "status", "--porcelain"]:
            return ""
        if command == [
            "git",
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{u}",
        ]:
            return "origin/main"
        if command == ["git", "rev-list", "--left-right", "--count", "HEAD...@{u}"]:
            return "0\t2"

        return unexpected_command(command, cwd)

    def runner(command: list[str], cwd: Path) -> None:
        """Do not run git or make commands for this test."""
        _run_fixture_make_all(command, cwd, workdir / "schema" / "example")

    prepare_release(
        product="example",
        version="1.1.0",
        repo_dir=workdir,
        submodules=[
            SubmoduleUpdate(identifier="vrs", branch="2.2.0-ballot", tag="v2.2.0")
        ],
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert "Warning: product branch is 2 commit(s) behind upstream." in messages


def test_prepare_release_skips_branch_warning_for_product_without_submodule(
    tmp_path: Path,
) -> None:
    """Do not warn about upstream branch freshness for first-chain products."""
    repo_dir = tmp_path / "gks-core"
    product_dir = repo_dir / "schema" / "gks-core"
    product_dir.mkdir(parents=True)
    (product_dir / "metaschema.yaml").write_text(
        "versions:\n  gks-core: 3.0.0\n",
        encoding="utf-8",
    )
    messages: list[str] = []
    commands: list[tuple[list[str], Path]] = []

    def runner(command: list[str], cwd: Path) -> None:
        """Record the build command without running make."""
        commands.append((command, cwd))

    def output_runner(command: list[str], cwd: Path) -> str:
        """Only allow the clean worktree check."""
        commands.append((command, cwd))
        if command == ["git", "status", "--porcelain"]:
            return ""
        return unexpected_command(command, cwd)

    prepare_release(
        product="gks-core",
        version="3.0.0",
        repo_dir=repo_dir,
        submodules=None,
        runner=runner,
        output_runner=output_runner,
        reporter=messages.append,
    )

    assert not any(
        message.startswith("Warning: product branch") for message in messages
    )
    assert (["git", "status", "--porcelain"], repo_dir.resolve()) in commands
    assert all("@{u}" not in command for command, _cwd in commands)
